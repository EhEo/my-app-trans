"""실행파일/트레이용 아이콘(app.ico) 생성기.

트레이 아이콘(main.App._make_icon_image)과 동일한 '겹친 두 카드(가 / A)'
디자인을 멀티 해상도 .ico 로 만든다. 디자인을 바꾸면 이 파일을 실행해
app.ico 를 다시 생성한 뒤 빌드하면 된다.

    python make_icon.py
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.FreeTypeFont:
    win = os.environ.get("WINDIR", r"C:\Windows")
    for name in ("malgunbd.ttf", "malgun.ttf", "segoeuib.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(os.path.join(win, "Fonts", name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(size: int = 256) -> Image.Image:
    """배율에 맞춰 '가 / A' 번역기 아이콘을 그린다 (RGBA, 투명배경)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    blue = "#1a73e8"
    s = size / 256.0  # 256 기준 좌표를 요청 크기로 스케일
    font = _font(int(86 * s))

    d.rounded_rectangle((24 * s, 24 * s, 150 * s, 150 * s),
                        radius=int(24 * s), fill=blue)
    d.text((87 * s, 90 * s), "가", font=font, fill="#ffffff", anchor="mm")

    d.rounded_rectangle((106 * s, 106 * s, 232 * s, 232 * s),
                        radius=int(24 * s), fill="#ffffff",
                        outline=blue, width=max(2, int(6 * s)))
    d.text((169 * s, 172 * s), "A", font=font, fill=blue, anchor="mm")
    return img


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = render(256)
    # 각 크기를 개별 렌더링하면 작은 크기에서 더 또렷하다.
    frames = [render(n) for n in sizes]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
    base.save(out, format="ICO",
              sizes=[(n, n) for n in sizes], append_images=frames)
    print(f"생성됨: {out}  (크기: {sizes})")


if __name__ == "__main__":
    main()
