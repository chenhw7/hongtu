"""生成应用图标 hongtu.ico（构建时使用）"""
from PIL import Image, ImageDraw, ImageFont
import os

def generate_ico():
    """生成一个简洁的应用图标：蓝色圆角背景 + 白色H字母"""
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    images = []
    
    for size in sizes:
        img = Image.new('RGBA', size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # 蓝色背景圆角矩形
        margin = size[0] // 8
        draw.rounded_rectangle(
            [margin, margin, size[0] - margin, size[1] - margin],
            radius=size[0] // 5,
            fill=(41, 128, 185, 255),
        )
        
        # 白色H字母（居中）
        font_size = size[0] // 2
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), 'H', font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (size[0] - text_w) // 2
        y = (size[1] - text_h) // 2 - bbox[1]
        draw.text((x, y), 'H', fill='white', font=font)
        
        images.append(img)
    
    # 保存为ICO（包含多种尺寸）
    ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hongtu.ico')
    images[0].save(ico_path, format='ICO', sizes=[(s[0], s[1]) for s in sizes], append_images=images[1:])
    print(f'图标已生成: {ico_path}')

if __name__ == '__main__':
    generate_ico()
