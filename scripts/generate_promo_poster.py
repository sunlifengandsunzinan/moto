from PIL import Image, ImageDraw, ImageFont
import qrcode

WIDTH, HEIGHT = 1080, 1920
OUT_PATH = "/Users/Lifeng.Sun/workspace/Personal/app/static/promo_poster.png"
APP_NAME = "行途"
APP_URL = "https://www.xingtu.ltd/moto"
REAL_QR_PATHS = [
    "/Users/Lifeng.Sun/workspace/Personal/app/static/miniprogram_qr.png",
    "/Users/Lifeng.Sun/workspace/Personal/app/static/mini_program_qr.png",
    "/Users/Lifeng.Sun/workspace/Personal/app/static/qr_code.png",
    "/Users/Lifeng.Sun/workspace/Personal/app/static/qrcode.png",
]


def load_font(size, bold=False):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def add_gradient_background(draw, width, height, base_img):
    top = (5, 25, 48)
    bottom = (18, 56, 92)
    for y in range(height):
        ratio = y / max(1, height - 1)
        r = int(top[0] * (1 - ratio) + bottom[0] * ratio)
        g = int(top[1] * (1 - ratio) + bottom[1] * ratio)
        b = int(top[2] * (1 - ratio) + bottom[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    glow_positions = [
        (180, 240, 210, (255, 145, 75, 120)),
        (910, 260, 220, (52, 196, 255, 120)),
        (260, 1450, 230, (255, 205, 100, 120)),
    ]
    for cx, cy, radius, color in glow_positions:
        shape = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(shape)
        d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color)
        base_img.paste(shape, (0, 0), mask=shape)


def load_qr_image(size, payload):
    for path in REAL_QR_PATHS:
        try:
            qr_image = Image.open(path).convert("RGBA")
            return qr_image.resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            continue

    qr = qrcode.QRCode(version=3, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    return qr_image.resize((size, size), Image.Resampling.LANCZOS)


def add_qr_code(img, center_x, center_y, size, payload):
    qr_image = load_qr_image(size, payload)
    x = center_x - size // 2
    y = center_y - size // 2
    border = Image.new("RGBA", (size + 24, size + 24), (255, 255, 255, 0))
    d = ImageDraw.Draw(border)
    d.rounded_rectangle((0, 0, size + 23, size + 23), radius=28, fill=(255, 255, 255, 200), outline=(206, 224, 243, 255), width=3)
    img.paste(border, (x - 12, y - 12), border)
    img.paste(qr_image, (x, y), qr_image)


def draw_phone_mock(draw, x, y, w, h):
    draw.rounded_rectangle((x, y, x + w, y + h), radius=42, fill=(14, 25, 43), outline=(70, 99, 135), width=4)
    draw.rounded_rectangle((x + 20, y + 20, x + w - 20, y + h - 20), radius=30, fill=(18, 33, 54))
    draw.rounded_rectangle((x + 40, y + 38, x + w - 40, y + 78), radius=16, fill=(17, 30, 46))
    draw.rounded_rectangle((x + 40, y + 110, x + w - 40, y + 330), radius=20, fill=(32, 58, 87))
    draw.rounded_rectangle((x + 40, y + 350, x + w - 40, y + 610), radius=20, fill=(32, 76, 108))
    # Keep the bottom module inside the phone frame so it doesn't overlap the QR area.
    draw.rounded_rectangle((x + 40, y + 620, x + w - 40, y + 740), radius=20, fill=(20, 40, 60))

    for start_x in [x + 58, x + 195, x + 332]:
        draw.rounded_rectangle((start_x, y + 146, start_x + 96, y + 180), radius=10, fill=(97, 180, 255))
    for start_x in [x + 58, x + 155, x + 250]:
        draw.rounded_rectangle((start_x, y + 212, start_x + 116, y + 244), radius=10, fill=(255, 165, 87))
    for i in range(0, 200, 20):
        draw.line((x + 70 + i, y + 470, x + 90 + i, y + 540), fill=(255, 185, 75), width=5)
    draw.line((x + 150, y + 445, x + 230, y + 500, x + 330, y + 420), fill=(70, 212, 148), width=5)
    draw.ellipse((x + 330, y + 405, x + 360, y + 435), fill=(70, 212, 148))

    tab_y = y + h - 96
    for i, label in enumerate(["路线", "发现", "我"]):
        tx = x + 58 + i * 110
        draw.rounded_rectangle((tx, tab_y - 20, tx + 70, tab_y + 30), radius=14, fill=(11, 22, 37))
        draw.text((tx + 35, tab_y + 5), label, font=load_font(20), anchor="mm", fill=(220, 234, 255))


def draw_card(draw, x, y, w, h, title, body, accent):
    draw.rounded_rectangle((x, y, x + w, y + h), radius=28, fill=(18, 35, 63), outline=(72, 100, 140), width=2)
    draw.rounded_rectangle((x + 22, y + 20, x + 54, y + 52), radius=12, fill=accent)
    draw.text((x + 78, y + 26), title, font=load_font(30, bold=True), fill=(255, 255, 255))
    draw.multiline_text((x + 28, y + 72), body, font=load_font(22), fill=(184, 202, 229), spacing=8)


img = Image.new("RGBA", (WIDTH, HEIGHT), (12, 18, 26, 255))
draw = ImageDraw.Draw(img)
add_gradient_background(draw, WIDTH, HEIGHT, img)

# badge and app name
badge_color = (255, 170, 90, 220)
draw.rounded_rectangle((90, 110, 360, 170), radius=24, fill=badge_color)
draw.text((225, 140), "小程序 · 行途", font=load_font(28, bold=True), fill=(25, 30, 39), anchor="mm")

draw.text((100, 220), APP_NAME, font=load_font(150, bold=True), fill=(245, 249, 255))
draw.text((105, 400), "路线 · 景点 · 收藏", font=load_font(42, bold=True), fill=(201, 223, 255))
draw.text((105, 470), "路线详情可复制到浏览器，直接在高德地图打开", font=load_font(28), fill=(186, 210, 232))

# feature cards
card_rows = [
    (90, 610, 300, 180, "路线规划", "按天定制路线\n里程、补给、停留清晰可见", (255, 149, 83)),
    (430, 610, 300, 180, "景点推荐", "按区域筛选\n热门打卡点、详情速览", (91, 192, 255)),
    (770, 610, 220, 180, "我的收藏", "路线收藏\n打卡记录、分享清单", (93, 215, 154)),
]
for x, y, w, h, title, body, accent in card_rows:
    draw_card(draw, x, y, w, h, title, body, accent)

# lower info panel
panel_y = 860
panel_h = 500
panel_x = 80
panel_w = 660
draw.rounded_rectangle((panel_x, panel_y, panel_x + panel_w, panel_y + panel_h), radius=34, fill=(15, 28, 46, 200), outline=(88, 113, 165), width=2)
draw.text((110, 900), "核心功能", font=load_font(34, bold=True), fill=(247, 250, 255))
feature_list = [
    "· 路线详情：复制到浏览器后可直接打开高德地图路线",
    "· 景点库：热门打卡点、区域筛选、详情查看",
    "· 个人收藏：收藏路线、打卡记录、分享成片",
    "· 轻量使用：小程序入口简单好用，适合传播转发",
]
for idx, item in enumerate(feature_list):
    draw.text((110, 960 + idx * 82), item, font=load_font(25), fill=(183, 207, 233))

# QR code on right
add_qr_code(img, 840, 1270, 320, APP_URL)
draw.text((840, 1498), "扫码打开", font=load_font(32, bold=True), fill=(255, 255, 255), anchor="mm")
draw.text((840, 1543), "行途小程序", font=load_font(26), fill=(188, 206, 245), anchor="mm")

# footer CTA
cta_y = 1605
cta_x1 = 90
cta_x2 = 990
draw.rounded_rectangle((cta_x1, cta_y, cta_x2, 1765), radius=32, fill=(255, 170, 90), outline=(255, 200, 150), width=2)
draw.text((540, 1660), "打开小程序 · 发现更适合你的路线", font=load_font(40, bold=True), fill=(30, 34, 45), anchor="mm")
draw.text((540, 1715), "路线 · 景点 · 收藏 · 打卡 · 分享", font=load_font(24), fill=(45, 58, 69), anchor="mm")

# phone mock preview on right side
phone_x, phone_y, phone_w, phone_h = 700, 250, 290, 760
draw_phone_mock(draw, phone_x, phone_y, phone_w, phone_h)

# save and print
img = img.convert("RGB")
img.save(OUT_PATH)
print(f"Poster saved to: {OUT_PATH}")
