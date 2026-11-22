"""Six fun themes, each with its own decoration and a corner picture:

  Space        - dark galaxy glass, twinkling star dust, purple/blue glow, planet + rocket
  Cozy Cabin   - wood frame with a red plaid band around cream "paper", log cabin
  Holiday      - deep red glass ringed with coloured string lights, tree + present
  Winter       - icy see-through glass with frosted corners and snowflakes, snowman
  Springfield  - cartoon-town yellow with thick black outlines, pink donut
                 (an original look-alike style, no copyrighted characters)
  Doghouse     - white comic-strip panels with thick ink outlines, red doghouse
                 (an original look-alike style, no copyrighted characters)

The decorations are painted by decor.py, the corner pictures live in assets/corners.
"""


def make(clean, neon):
    def light(**kw):
        t = dict(clean)
        t.update(strip_height=0, glow=False)
        t.update(kw)
        return t

    def dark(**kw):
        t = dict(neon)
        t.update(strip_height=0, glow=False)
        t.update(kw)
        return t

    space = dark(
        name="Space", glow=True, glow_scale=0.75, decor="stars", corner="space",
        rgb_stops=[(120, 80, 255), (60, 140, 255), (190, 90, 255), (70, 200, 255), (140, 90, 255), (80, 120, 255)],
        glass_fill=(10, 12, 40, 200), glass_fill_hover=(18, 20, 58, 218), glass_border=(150, 150, 255, 120),
        panel_fill=(9, 11, 36, 214), popup_fill=(8, 10, 30, 238),
        accent=(124, 107, 255, 255), default_accent="#7C6BFF", dock_handle=(150, 120, 255, 190),
        card_fill=(120, 130, 255, 18), card_fill_hot=(140, 150, 255, 40), card_border=(150, 160, 255, 40))

    brown = (70, 42, 20, 255)
    cabin = light(
        name="Cozy Cabin", decor="plaid", corner="cabin", border_w=2.0, radius_scale=0.55,
        glass_fill=(246, 236, 214, 236), glass_fill_hover=(250, 242, 224, 246), glass_border=(78, 46, 22, 255),
        glass_shine=(255, 250, 235, 30), panel_fill=(246, 236, 214, 240), popup_fill=(248, 240, 222, 248),
        panel_text=brown, title_text=brown, panel_title_text=brown, search_text=brown, button_text=brown,
        panel_subtext=(110, 80, 55, 255), hint_text=(120, 92, 66, 255), icon_glyph=(96, 64, 38, 255),
        dot_on=(90, 56, 30, 220), dot_off=(90, 56, 30, 70), divider=(80, 50, 25, 40),
        card_fill=(255, 250, 238, 200), card_fill_hot=(255, 252, 244, 250), card_border=(110, 70, 40, 50),
        accent=(198, 140, 80, 255), default_accent="#C68C50", dock_handle=(150, 100, 60, 190),
        shadow=(40, 20, 0, 50))

    cream = (255, 236, 200, 255)
    holiday = dark(
        name="Holiday", decor="lights", corner="holiday", border_w=1.5,
        glass_fill=(112, 14, 24, 218), glass_fill_hover=(130, 20, 30, 232), glass_border=(232, 190, 110, 190),
        glass_shine=(255, 220, 180, 16), panel_fill=(104, 12, 22, 226), popup_fill=(92, 10, 18, 242),
        panel_text=cream, search_text=cream, button_text=cream, title_text=(244, 204, 120, 255),
        panel_title_text=(244, 204, 120, 255), panel_subtext=(240, 210, 180, 255), hint_text=(232, 196, 160, 255),
        icon_glyph=(244, 210, 150, 255), card_fill=(255, 220, 160, 20), card_fill_hot=(255, 220, 160, 44),
        card_border=(240, 200, 120, 50), accent=(232, 176, 74, 255), default_accent="#E8B04A",
        dock_handle=(232, 176, 74, 200))

    navy = (22, 44, 78, 255)
    winter = light(
        name="Winter", decor="frost", corner="winter", border_w=2.0,
        glass_fill=(214, 232, 250, 150), glass_fill_hover=(226, 240, 252, 190), glass_border=(255, 255, 255, 245),
        glass_shine=(255, 255, 255, 110), panel_fill=(220, 236, 250, 190), popup_fill=(232, 243, 253, 240),
        panel_text=navy, title_text=navy, panel_title_text=navy, search_text=navy, button_text=navy,
        panel_subtext=(70, 96, 130, 255), hint_text=(80, 106, 140, 255), icon_glyph=(60, 90, 130, 255),
        card_fill=(255, 255, 255, 120), card_fill_hot=(255, 255, 255, 200), card_border=(120, 160, 210, 70),
        accent=(90, 169, 230, 255), default_accent="#5AA9E6", dock_handle=(255, 255, 255, 200))

    ink = (20, 20, 20, 255)
    springfield = light(
        name="Springfield", decor="cartoon", corner="springfield", border_w=3.0, radius_scale=0.7,
        glass_fill=(255, 217, 15, 242), glass_fill_hover=(255, 224, 60, 250), glass_border=ink,
        glass_shine=(255, 255, 255, 30), panel_fill=(255, 217, 15, 244), popup_fill=(255, 222, 40, 250),
        panel_text=ink, title_text=ink, panel_title_text=ink, search_text=ink, button_text=ink,
        panel_subtext=(60, 50, 10, 255), hint_text=(80, 70, 20, 255), icon_glyph=ink,
        card_fill=(255, 241, 150, 235), card_fill_hot=(255, 248, 200, 255), card_border=(20, 20, 20, 120),
        accent=(61, 139, 255, 255), default_accent="#3D8BFF", dock_handle=(20, 20, 20, 160),
        shadow=(0, 0, 0, 40))

    doghouse = light(
        name="Doghouse", decor="comic", corner="doghouse", border_w=3.0, radius_scale=0.75,
        glass_fill=(255, 255, 255, 246), glass_fill_hover=(255, 255, 255, 252), glass_border=ink,
        glass_shine=(255, 255, 255, 0), panel_fill=(255, 255, 255, 248), popup_fill=(255, 255, 255, 252),
        panel_text=ink, title_text=ink, panel_title_text=ink, search_text=ink, button_text=ink,
        panel_subtext=(70, 70, 70, 255), hint_text=(90, 90, 90, 255), icon_glyph=ink,
        card_fill=(255, 255, 255, 255), card_fill_hot=(245, 245, 245, 255), card_border=(20, 20, 20, 90),
        accent=(224, 50, 43, 255), default_accent="#E0322B", dock_handle=(20, 20, 20, 160),
        shadow=(0, 0, 0, 40))

    return {t["name"]: t for t in (space, cabin, holiday, winter, springfield, doghouse)}
