import os
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from collections import Counter
from anony import config
from anony.helpers import Track


class Thumbnail:
    def __init__(self):
        self.size = (1280, 720)
        self.font_title = ImageFont.truetype("anony/helpers/NotoSans-Bold.ttf", 32)
        self.font_info = ImageFont.truetype("anony/helpers/font2.ttf", 28)
        self.font_play = ImageFont.truetype("anony/helpers/NotoSans-Bold.ttf", 32)
        
        self.card_fill = (235, 235, 235, 220)
        self.card_border = (220, 220, 220, 200)
        self.fill = (255, 255, 255, 235)
        self.margin_x = 80
        self.margin_y = 60

    async def save_thumb(self, output_path: str, url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.read()
                with open(output_path, "wb") as f:
                    f.write(data)
        return output_path

    def _truncate_text(self, draw, text, font, max_width):
        if draw.textlength(text, font=font) <= max_width:
            return text
        words = text.split()
        out = ""
        for w in words:
            candidate = (out + " " + w).strip() if out else w
            if draw.textlength(candidate + ".", font=font) <= max_width:
                out = candidate
            else:
                break
        return out + "." if out else text[:10] + "."

    def _get_dominant_colors(self, image, n=2):
        img = image.resize((100, 100)).convert("RGB")
        return [c[0] for c in Counter(img.getdata()).most_common(n)]

    async def generate(self, song: Track) -> str:
        try:
            temp = f"cache/temp_{song.id}.jpg"
            output = f"cache/{song.id}.png"
            if os.path.exists(output):
                return output

            await self.save_thumb(temp, song.thumbnail)
            cover = Image.open(temp).convert("RGBA").resize(self.size, Image.Resampling.LANCZOS)

            bg = cover.filter(ImageFilter.GaussianBlur(32))
            bg = ImageEnhance.Brightness(bg).enhance(0.42)
            bg = Image.alpha_composite(bg, Image.new("RGBA", self.size, (0, 0, 0, 10)))

            vignette = Image.new("L", self.size, 0)
            draw_v = ImageDraw.Draw(vignette)
            draw_v.ellipse((-200, -100, self.size[0] + 200, self.size[1] + 300), fill=255)
            vignette = vignette.filter(ImageFilter.GaussianBlur(2))
            bg.putalpha(vignette)

            portrait_size = (520, 480)
            portrait = ImageOps.fit(cover, portrait_size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            mask = Image.new("L", portrait_size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, *portrait_size), radius=40, fill=255)
            portrait.putalpha(mask)

            shadow = Image.new("RGBA", (portrait_size[0] + 40, portrait_size[1] + 40), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).rounded_rectangle(
                (10, 10, portrait_size[0] + 10, portrait_size[1] + 10), radius=40, fill=(0, 0, 0, 180)
            )

            center_x = self.size[0] // 2
            portrait_x = center_x - portrait_size[0] // 2
            portrait_y = self.margin_y

            glow_padding = 32
            glow_size = (portrait_size[0] + glow_padding * 2, portrait_size[1] + glow_padding * 2)
            glow_mask = Image.new("L", glow_size, 0)
            ImageDraw.Draw(glow_mask).rounded_rectangle(
                (0, 0, *glow_size), radius=40 + glow_padding // 2, fill=255
            )
            glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(36))

            dominant = self._get_dominant_colors(cover, n=1)[0] if cover else (255, 255, 255)
            colored_glow = Image.composite(
                Image.new("RGBA", glow_size, (*dominant, 80)),
                Image.new("RGBA", glow_size, (0, 0, 0, 0)),
                glow_mask.filter(ImageFilter.GaussianBlur(22))
            )

            glow_layer = Image.new("RGBA", self.size, (0, 0, 0, 0))
            glow_layer.paste(colored_glow, (portrait_x - glow_padding, portrait_y - glow_padding), colored_glow)
            bg = Image.alpha_composite(bg, glow_layer)

            bg.paste(shadow, (portrait_x, portrait_y + 12), shadow)
            bg.paste(portrait, (portrait_x, portrait_y), portrait)

            draw = ImageDraw.Draw(bg)
            text_top = portrait_y + portrait_size[1] + 40
            safe_width = self.size[0] - self.margin_x * 2

            title_text = self._truncate_text(draw, song.title, self.font_title, safe_width - 36)
            info_text = f"{song.channel_name[:40]} • {song.view_count} views"
            info_text = self._truncate_text(draw, info_text, self.font_info, safe_width - 36)

            title_h = draw.textbbox((0, 0), title_text, font=self.font_title)[3] - draw.textbbox((0, 0), title_text, font=self.font_title)[1]

            draw.text((center_x, text_top), title_text, font=self.font_title, fill=(255, 255, 255, 255), anchor="ma")
            draw.text((center_x, text_top + title_h + 10), info_text, font=self.font_info, fill=(255, 248, 230, 255), anchor="ma")

            bar_width = 12
            bar_x = self.size[0] - self.margin_x
            bar_top = portrait_y + 10
            bar_bottom = max(text_top - 20, portrait_y + portrait_size[1] - 10)

            track_left = bar_x - bar_width // 2
            track_right = bar_x + bar_width // 2

            track_layer = Image.new("RGBA", self.size, (0, 0, 0, 0))
            tdraw = ImageDraw.Draw(track_layer)
            tdraw.rounded_rectangle((track_left, bar_top, track_right, bar_bottom), bar_width, fill=(255, 255, 255, 140))
            bg = Image.alpha_composite(bg, track_layer.filter(ImageFilter.GaussianBlur(1)))

            fill_fraction = 0.6
            progress_h = int((bar_bottom - bar_top) * fill_fraction)
            fill_top_y = bar_bottom - progress_h

            fill_layer = Image.new("RGBA", self.size, (0, 0, 0, 0))
            ImageDraw.Draw(fill_layer).rounded_rectangle(
                (track_left, fill_top_y, track_right, bar_bottom), bar_width, fill=(*dominant, 255)
            )
            bg = Image.alpha_composite(bg, fill_layer.filter(ImageFilter.GaussianBlur(2)))

            draw.text((bar_x - 12, bar_top - 40), "0:00", font=self.font_info, fill=self.fill, anchor="rs")
            draw.text((bar_x - 12, bar_bottom + 10), "0:30", font=self.font_info, fill=self.fill, anchor="rs")

            bg.save(output, "PNG")
            os.remove(temp)
            return output

        except Exception as e:
            print(f"Thumbnail generation failed: {e}")
            return config.DEFAULT_THUMB
