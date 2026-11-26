import math

import pygame
import pymunk

# 키보드로 테스트할 때는 None, ESP32을 연결할 때는 실제 포트명 사용
PORT = None  # 예: "COM5"
BAUD_RATE = 115200

WIDTH, HEIGHT = 900, 480
GROUND_Y = 430
START_X, START_Y = 100, 360
BALL_RADIUS = 10
GRAVITY = 480       # 픽셀/s²
MIN_PULL = 5       # 이 값 미만이면 발사하지 않음
MAX_SPEED = 740    # 픽셀/s

# 물리 설정
PHYSICS_STEP = 1 / 240      # 고정 시간 간격으로 시뮬레이션해야 쌓인 블록이 안정적이다
BALL_MASS = 6.0
WOOD_DENSITY = 0.003        # 픽셀 면적당 질량 (클수록 무거워서 잘 안 넘어진다)
WOOD_FRICTION = 0.8
WOOD_ELASTICITY = 0.05
KNOCK_ANGLE = math.radians(35)  # 이 각도 이상 기울면 쓰러진 것으로 본다
KNOCK_DROP = 18                 # 이만큼 아래로 떨어져도 쓰러진 것으로 본다
SETTLE_TIME = 0.3               # 쓰러진 블록이 이 시간 동안 멈춰 있으면 사라진다
BALL_REST_TIME = 0.6           # 공이 이 시간 동안 거의 멈춰 있으면 다음 발사 가능
BALL_MAX_TIME = 7.0


def launch_velocity(pull, angle):
    speed = MAX_SPEED * pull / 100
    radians = math.radians(angle)

    # Pygame은 화면 아래쪽으로 갈수록 y 좌표가 커짐
    return speed * math.cos(radians), -speed * math.sin(radians)


# 각 스테이지는 아래층부터 기둥 높이, 가로판 위치와 폭, 기둥 위치와 폭을 지정한다.
STAGES = (
    (
        (78, 555, 225, ((563, 17), (623, 17), (664, 14), (750, 15))),
        (76, 562, 214, ((572, 17), (625, 17), (658, 17), (748, 13))),
        (59, 623, 137, ((630, 17), (704, 13), (723, 18))),
        (23, 0, 0, ((656, 18),)),
    ),
    (
        (102, 520, 287, ((535, 18), (644, 20), (766, 20))),
        (68, 566, 225, ((584, 18), (674, 16), (750, 20))),
        (53, 602, 134, ((613, 17), (700, 17))),
    ),
    (
        (76, 583, 238, ((596, 18), (690, 16), (787, 18))),
        (65, 609, 186, ((632, 18), (701, 18), (760, 18))),
        (58, 643, 142, ((654, 16), (747, 16))),
        (41, 673, 82, ((685, 14), (729, 14))),
    ),
)
STAGE_CLEAR_DELAY = 0.9


def create_space():
    space = pymunk.Space()
    space.gravity = (0, GRAVITY)
    space.iterations = 30
    # 가만히 있는 블록은 잠들게 해서 탑이 저절로 흔들리지 않게 한다.
    space.sleep_time_threshold = 0.4
    space.idle_speed_threshold = 4

    ground = pymunk.Segment(space.static_body, (-2000, GROUND_Y + 5),
                            (WIDTH + 2000, GROUND_Y + 5), 5)
    ground.friction = 1.0
    ground.elasticity = 0.1
    space.add(ground)
    return space


class Block:
    def __init__(self, space, rect):
        self.size = rect.size
        self.start_y = rect.centery
        mass = WOOD_DENSITY * rect.width * rect.height
        self.body = pymunk.Body(mass, pymunk.moment_for_box(mass, rect.size))
        self.body.position = rect.center
        self.shape = pymunk.Poly.create_box(self.body, rect.size)
        self.shape.friction = WOOD_FRICTION
        self.shape.elasticity = WOOD_ELASTICITY
        space.add(self.body, self.shape)

        self.surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        draw_wood(self.surface, self.surface.get_rect())
        self.knocked = False
        self.rest_time = 0.0

    def settled(self, dt):
        # 쓰러진 뒤 바닥이나 다른 블록 위에서 멈추면 True
        if not self.knocked:
            return False
        if self.body.velocity.length < 8 and abs(self.body.angular_velocity) < 0.3:
            self.rest_time += dt
        else:
            self.rest_time = 0.0
        return self.rest_time >= SETTLE_TIME

    def update_knocked(self):
        if self.knocked:
            return False
        tilt = abs(math.remainder(self.body.angle, math.pi))
        dropped = self.body.position.y - self.start_y
        out = not -50 <= self.body.position.x <= WIDTH + 50
        if tilt > KNOCK_ANGLE or dropped > KNOCK_DROP or out:
            self.knocked = True
            return True
        return False

    def draw(self, screen):
        x, y = self.body.position
        surface = pygame.transform.rotate(self.surface, -math.degrees(self.body.angle))
        screen.blit(surface, surface.get_rect(center=(round(x), round(y))))


def build_tower(space, stage_index):
    bottom = GROUND_Y
    blocks = []
    for height, board_left, board_width, posts in STAGES[stage_index]:
        top = bottom - height
        for left, width in posts:
            blocks.append(Block(space, pygame.Rect(left, top, width, height)))
        if board_width:
            blocks.append(Block(space, pygame.Rect(board_left, top - 8, board_width, 8)))
        bottom = top - 8
    return blocks


def remove_blocks(space, blocks):
    for block in blocks:
        space.remove(block.body, block.shape)


def create_ball(space, velocity):
    body = pymunk.Body(BALL_MASS, pymunk.moment_for_circle(BALL_MASS, 0, BALL_RADIUS))
    body.position = (START_X, START_Y)
    body.velocity = velocity
    shape = pymunk.Circle(body, BALL_RADIUS)
    shape.friction = 0.6
    shape.elasticity = 0.35
    space.add(body, shape)
    return body, shape


def draw_wood(screen, rect):
    vertical = rect.height > rect.width
    pygame.draw.rect(screen, (193, 119, 45), rect)
    pygame.draw.rect(screen, (104, 57, 28), rect, 1)
    pygame.draw.line(screen, (248, 186, 91),
                     (rect.left + 1, rect.top + 1),
                     (rect.left + 1, rect.bottom - 2) if vertical
                     else (rect.right - 2, rect.top + 1))
    if vertical:
        for offset in (4, 8):
            x = rect.left + offset
            pygame.draw.line(screen, (159, 91, 35),
                             (x, rect.top + 4), (x, rect.bottom - 5))
        for y in (rect.top + 3, rect.bottom - 4):
            pygame.draw.circle(screen, (113, 63, 31), (rect.centerx, y), 1)


def main():
    connection = None
    if PORT is not None:
        import serial

        connection = serial.Serial(PORT, BAUD_RATE, timeout=0)

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Sensor Slingshot")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 28)

    space = create_space()
    stage_index = 0
    stage_clear_time = 0.0
    blocks = build_tower(space, stage_index)
    score = 0
    pull, angle = 65.0, 40.0
    previous_button = 0
    serial_buffer = b""

    ball = None             # (body, shape)
    ball_time = 0.0
    ball_rest_time = 0.0
    accumulator = 0.0
    running = True

    try:
        while running:
            dt = min(clock.tick(60) / 1000, 0.05)
            launch_requested = False

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    launch_requested = True

            if connection is None:
                keys = pygame.key.get_pressed()
                pull += (keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]) * 60 * dt
                angle += (keys[pygame.K_UP] - keys[pygame.K_DOWN]) * 60 * dt
                pull = max(0, min(100, pull))
                angle = max(10, min(80, angle))
            else:
                # 줄 중간에서 끊겨 들어온 데이터는 다음 프레임까지 보관
                serial_buffer += connection.read(connection.in_waiting)
                lines = serial_buffer.split(b"\n")
                serial_buffer = lines.pop()

                for line in lines:
                    try:
                        raw_pull, raw_angle, raw_button = line.strip().split(b",")
                        new_pull = float(raw_pull)
                        new_angle = float(raw_angle)
                        button = int(raw_button)
                    except ValueError:
                        continue

                    if not (0 <= new_pull <= 100 and 10 <= new_angle <= 80):
                        continue
                    if button not in (0, 1):
                        continue

                    pull, angle = new_pull, new_angle
                    if previous_button == 0 and button == 1:
                        if pull >= MIN_PULL:
                            # 버튼을 누른 순간의 센서값으로 발사
                            launch_requested = (pull, angle)
                    previous_button = button

            standing = [block for block in blocks if not block.knocked]

            if launch_requested and ball is None and standing:
                if launch_requested is True:
                    launch_pull, launch_angle = pull, angle
                else:
                    launch_pull, launch_angle = launch_requested

                if launch_pull >= MIN_PULL:
                    ball = create_ball(space, launch_velocity(launch_pull, launch_angle))
                    ball_time = ball_rest_time = 0.0

            # 고정 간격으로 물리 시뮬레이션 (블록끼리 부딪히며 연쇄적으로 쓰러진다)
            accumulator += dt
            while accumulator >= PHYSICS_STEP:
                space.step(PHYSICS_STEP)
                accumulator -= PHYSICS_STEP

            for block in blocks:
                if block.update_knocked():
                    score += 100

            # 쓰러져서 멈춘 블록과 화면 밖으로 나간 블록은 제거
            gone = [block for block in blocks
                    if block.settled(dt)
                    or not -100 <= block.body.position.x <= WIDTH + 100]
            if gone:
                remove_blocks(space, gone)
                blocks = [block for block in blocks if block not in gone]

            if ball is not None:
                body, shape = ball
                ball_time += dt
                if body.velocity.length < 20:
                    ball_rest_time += dt
                else:
                    ball_rest_time = 0.0
                x, _ = body.position
                if (ball_rest_time > BALL_REST_TIME or ball_time > BALL_MAX_TIME
                        or not -BALL_RADIUS <= x <= WIDTH + BALL_RADIUS):
                    space.remove(body, shape)
                    ball = None

            standing = [block for block in blocks if not block.knocked]
            if not standing and ball is None and stage_index + 1 < len(STAGES):
                stage_clear_time += dt
                if stage_clear_time >= STAGE_CLEAR_DELAY:
                    stage_index += 1
                    remove_blocks(space, blocks)
                    blocks = build_tower(space, stage_index)
                    stage_clear_time = 0.0

            screen.fill((0, 0, 0))
            pygame.draw.line(screen, (175, 175, 175), (0, GROUND_Y), (WIDTH, GROUND_Y))
            pygame.draw.lines(screen, (205, 205, 205), False,
                              [(START_X - 17, START_Y - 9), (START_X, START_Y + 22),
                               (START_X + 17, START_Y - 9)], 4)
            pygame.draw.line(screen, (205, 205, 205),
                             (START_X, START_Y + 22), (START_X, GROUND_Y), 4)

            for block in blocks:
                block.draw(screen)

            if ball is not None:
                bx, by = ball[0].position
                ball_center = (round(bx), round(by))
            else:
                ball_center = (START_X, START_Y)
                # 미리보기에도 실제 발사와 같은 포물선 식을 사용
                preview_vx, preview_vy = launch_velocity(pull, angle)
                if standing and pull >= MIN_PULL:
                    for i in range(1, 45):
                        t = i * 0.04
                        px = START_X + preview_vx * t
                        py = START_Y + preview_vy * t + 0.5 * GRAVITY * t**2
                        if (py + BALL_RADIUS >= GROUND_Y or px > WIDTH
                                or any(block.shape.point_query((px, py)).distance <= BALL_RADIUS
                                       for block in blocks)):
                            break
                        pygame.draw.circle(screen, (150, 150, 150),
                                           (round(px), round(py)), 3)

            pygame.draw.circle(screen, (255, 255, 255), ball_center, BALL_RADIUS)

            status = (
                f"Stage {stage_index + 1}/{len(STAGES)}    "
                f"Pull {pull:.0f}%    Angle {angle:.0f} deg    Score {score}"
            )
            screen.blit(font.render(status, True, (230, 230, 230)), (20, 20))
            if not standing:
                message = "All stages clear!" if stage_index + 1 == len(STAGES) else "Stage clear!"
                screen.blit(font.render(message, True, (230, 230, 230)), (20, 52))

            pygame.display.flip()
    finally:
        if connection is not None:
            connection.close()
        pygame.quit()


if __name__ == "__main__":
    main()
