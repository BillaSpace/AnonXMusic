import os
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from collections import Counter
from anony import config
from anony.helpers import Track


class Thumbnail:
    def __init__(self):
        self.size = (1280, 720)
        self.font_title = ImageFont.truetype("anony/helpers/font.ttf", 28)
        self.font_info = ImageFont.truetype("anony/helpers/font2.ttf", 28)
        self.font_play = ImageFont.truetype("anony/helpers/DejaVuSans.ttf", 32)

        self.card_fill = (235, 235, 235, 220)
        self.card_border = (220, 220, 220, 200)
        self.fill = (255, 255, 255, 235)
        self.margin_x = 80
        self.margin_y = 60

    async def save_thumb(self, output_path: str, url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                with open(output_path, "wb") as f:
                    f.write(await resp.read())
        return output_path

    def _truncate_text(self, draw, text, font, max_width):
        if draw.textlength(text, font=font) <= max_width:
            return text
        words = text.split()
        out = ""
        for w in words:
            candidate = (out + " " + w).strip()
            if draw.textlength(candidate + ".", font=font) <= max_width:
                out = candidate
            else:
                break
        return out.strip() + "."

    def _get_dominant_colors(self, image, n=2):
        img = image.copy().resize((100, 100)).convert("RGB")
        pixels = list(img.getdata())
        return [c[0] for c in Counter(pixels).most_common(n)]

    def _mix_colors(self, color1, color2):
        return tuple(int((c1 + c2) / 2) for c1, c2 in zip(color1, color2))

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
            dark_overlay = Image.new("RGBA", bg.size, (0, 0, 0, 10))
            bg = Image.alpha_composite(bg, dark_overlay)

            vignette = Image.new("L", self.size, 0)
            draw_v = ImageDraw.Draw(vignette)
            draw_v.ellipse((-200, -100, self.size[0] + 200, self.size[1] + 300), fill=255)
            vignette = vignette.filter(ImageFilter.GaussianBlur(2))
            bg.putalpha(vignette)

            portrait_size = (520, 480)
            portrait = ImageOps.fit(cover, portrait_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            mask = Image.new("L", portrait_size, 0)
            mdraw = ImageDraw.Draw(mask)
            corner_radius = 40
            mdraw.rounded_rectangle((0, 0, portrait_size[0], portrait_size[1]), corner_radius, fill=255)
            portrait.putalpha(mask)

            shadow = Image.new("RGBA", (portrait_size[0] + 40, portrait_size[1] + 40), (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_draw.rounded_rectangle(
                (10, 10, portrait_size[0] + 10, portrait_size[1] + 10), corner_radius, fill=(0, 0, 0, 180)
            )

            center_x = self.size[0] // 2
            portrait_x = center_x - portrait_size[0] // 2
            portrait_y = self.margin_y

            glow_padding = 32
            glow_size = (portrait_size[0] + glow_padding * 2, portrait_size[1] + glow_padding * 2)
            glow_mask = Image.new("L", glow_size, 0)
            gdraw = ImageDraw.Draw(glow_mask)
            gdraw.rounded_rectangle(
                (0, 0, glow_size[0], glow_size[1]),
                corner_radius + glow_padding // 2,
                fill=255
            )
            glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(36))

            colors = self._get_dominant_colors(cover)
            if not colors:
                colors = [(255, 255, 255)]
            dominant = colors[0]

            glow_color_img = Image.new("RGBA", glow_size, (*dominant, 80))
            colored_glow = Image.new("RGBA", glow_size, (0, 0, 0, 0))
            colored_glow.paste(glow_color_img, (0, 0), glow_mask)
            colored_glow = colored_glow.filter(ImageFilter.GaussianBlur(22))

            glow_layer = Image.new("RGBA", bg.size, (0, 0, 0, 0))
            glow_pos = (portrait_x - glow_padding, portrait_y - glow_padding)
            glow_layer.paste(colored_glow, glow_pos, colored_glow)
            bg = Image.alpha_composite(bg, glow_layer)

            bg.paste(shadow, (portrait_x, portrait_y + 12), shadow)
            bg.paste(portrait, (portrait_x, portrait_y), portrait)

            draw = ImageDraw.Draw(bg)

            text_top = portrait_y + portrait_size[1] + 40
            safe_width = self.size[0] - (self.margin_x * 2)
            card_padding = 18

            title_text = self._truncate_text(draw, song.title, self.font_title, safe_width - card_padding * 2)
            channel_text = song.channel_name[:40]
            info_text = f"{channel_text} • {song.view_count} views"
            info_text = self._truncate_text(draw, info_text, self.font_info, safe_width - card_padding * 2)

            title_bbox = draw.textbbox((0, 0), title_text, font=self.font_title)
            info_bbox = draw.textbbox((0, 0), info_text, font=self.font_info)
            title_h = title_bbox[3] - title_bbox[1]

            text_center_x = self.size[0] // 2
            draw.text((text_center_x, text_top), title_text, font=self.font_title, fill=(255, 255, 255, 255), anchor="ma")
            draw.text((text_center_x, text_top + title_h + 6), info_text, font=self.font_info, fill=(255, 248, 230, 255), anchor="ma")

            bar_width = 12
            bar_x = self.size[0] - self.margin_x
            bar_top = portrait_y + 10
            bar_bottom = text_top - 20
            if bar_bottom <= bar_top + 20:
                bar_bottom = portrait_y + portrait_size[1] - 10

            track_layer = Image.new("RGBA", bg.size, (0, 0, 0, 0))
            tdraw = ImageDraw.Draw(track_layer)
            track_left = bar_x - bar_width // 2
            track_right = bar_x + bar_width // 2
            tdraw.rounded_rectangle((track_left, bar_top, track_right, bar_bottom), bar_width, fill=(255, 255, 255, 140))
            track_layer = track_layer.filter(ImageFilter.GaussianBlur(1))
            bg = Image.alpha_composite(bg, track_layer)

            fill_fraction = 0.6
            total_height = (bar_bottom - bar_top)
            progress_height = int(total_height * fill_fraction)
            fill_top_y = bar_bottom - progress_height

            bar_fill_layer = Image.new("RGBA", bg.size, (0, 0, 0, 0))
            bf_draw = ImageDraw.Draw(bar_fill_layer)
            bf_draw.rounded_rectangle((track_left, fill_top_y, track_right, bar_bottom), bar_width, fill=(*dominant, 255))
            bar_fill_layer = bar_fill_layer.filter(ImageFilter.GaussianBlur(2))
            bg = Image.alpha_composite(bg, bar_fill_layer)


            play_icon = "▷"
            play_x = bar_x + bar_width + 12
            play_y = fill_top_y + progress_height // 2
            draw.text((play_x, play_y), play_icon, font=self.font_play, fill=(*dominant, 255), anchor="lm")

            draw.text((bar_x - 12, bar_top - 40), "0:00", font=self.font_info, fill=self.fill, anchor="rs")
            draw.text((bar_x - 12, bar_bottom + 10), "0:30", font=self.font_info, fill=self.fill, anchor="rs")

            bg.save(output, "PNG")
            os.remove(temp)
            return output

        except Exception as e:
            print(f"Thumbnail generation failed: {e}")
            return config.DEFAULT_THUMB
