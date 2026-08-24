from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math


WIDTH, HEIGHT = 3840, 2160
BG = "#F7F9FC"
TEXT = "#172033"
MUTED = "#5B6475"
LINE = "#687386"
WHITE = "#FFFFFF"

FONT_REGULAR = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

title_font = ImageFont.truetype(FONT_BOLD, 76)
subtitle_font = ImageFont.truetype(FONT_REGULAR, 34)
panel_font = ImageFont.truetype(FONT_BOLD, 44)
node_font = ImageFont.truetype(FONT_BOLD, 34)
small_font = ImageFont.truetype(FONT_REGULAR, 28)
legend_font = ImageFont.truetype(FONT_REGULAR, 30)

img = Image.new("RGB", (WIDTH, HEIGHT), BG)
draw = ImageDraw.Draw(img)


def rounded_box(box, radius, fill, outline, width=4):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def centered_text(box, text, font, fill=TEXT, spacing=10):
    x1, y1, x2, y2 = box
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align="center")
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.multiline_text(
        ((x1 + x2 - tw) / 2, (y1 + y2 - th) / 2 - 3),
        text,
        font=font,
        fill=fill,
        spacing=spacing,
        align="center",
    )


def node(box, text, kind="process"):
    if kind == "agent":
        fill, outline = "#EEE7FF", "#7B55D9"
    elif kind == "start":
        fill, outline = "#DDEAFF", "#246BCE"
    elif kind == "end":
        fill, outline = "#D8F3E4", "#198754"
    elif kind == "input":
        fill, outline = "#E4F7F4", "#228B7E"
    else:
        fill, outline = WHITE, "#9BA6B7"
    rounded_box(box, 28 if kind in {"start", "end"} else 20, fill, outline, 5)
    centered_text(box, text, node_font)


def diamond(center, size, text):
    cx, cy = center
    w, h = size
    pts = [(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)]
    draw.polygon(pts, fill="#FFF2C9", outline="#D79B16")
    draw.line(pts + [pts[0]], fill="#D79B16", width=5, joint="curve")
    centered_text((cx - w / 2 + 25, cy - h / 2 + 20, cx + w / 2 - 25, cy + h / 2 - 20), text, node_font)


def arrow(points, label=None, dashed=False, color=LINE, width=7):
    if dashed:
        dash, gap = 20, 13
        for a, b in zip(points, points[1:]):
            x1, y1 = a
            x2, y2 = b
            length = math.hypot(x2 - x1, y2 - y1)
            if not length:
                continue
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            pos = 0
            while pos < length:
                seg_end = min(pos + dash, length)
                draw.line(
                    (x1 + ux * pos, y1 + uy * pos, x1 + ux * seg_end, y1 + uy * seg_end),
                    fill=color,
                    width=width,
                )
                pos += dash + gap
    else:
        draw.line(points, fill=color, width=width, joint="curve")

    x1, y1 = points[-2]
    x2, y2 = points[-1]
    angle = math.atan2(y2 - y1, x2 - x1)
    head = 24
    wing = 0.58
    p1 = (x2 - head * math.cos(angle - wing), y2 - head * math.sin(angle - wing))
    p2 = (x2 - head * math.cos(angle + wing), y2 - head * math.sin(angle + wing))
    draw.polygon([(x2, y2), p1, p2], fill=color)

    if label:
        mid_index = max(0, len(points) // 2 - 1)
        ax, ay = points[mid_index]
        bx, by = points[mid_index + 1]
        mx, my = (ax + bx) / 2, (ay + by) / 2
        tb = draw.textbbox((0, 0), label, font=small_font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        label_box = (mx - tw / 2 - 12, my - th / 2 - 7, mx + tw / 2 + 12, my + th / 2 + 7)
        rounded_box(label_box, 10, BG, None, 0)
        draw.text((mx - tw / 2, my - th / 2 - 2), label, font=small_font, fill=MUTED)


def panel(box, title, fill, stroke):
    rounded_box(box, 30, fill, stroke, 4)
    draw.text((box[0] + 38, box[1] + 24), title, font=panel_font, fill=TEXT)


# Header
draw.text((120, 58), "Python 人力资源 Agent 业务流程图", font=title_font, fill=TEXT)
draw.text(
    (122, 154),
    "员工全生命周期：招聘 → 入职 → 在职服务 → 绩效发展 → 离职归档",
    font=subtitle_font,
    fill=MUTED,
)

# Phase panels
panel((100, 245, 3740, 700), "01  招聘管理", "#EAF4FF", "#8BC5F5")
panel((100, 770, 1450, 1195), "02  入职管理", "#ECF8EF", "#89D59B")
panel((1530, 770, 3740, 1195), "03  在职员工服务", "#E8F9F7", "#7ED7CD")
panel((100, 1270, 2250, 1810), "04  绩效与人才发展", "#FFF8E3", "#E8C45A")
panel((2330, 1270, 3740, 1810), "05  离职管理", "#FFF0EC", "#F2A08D")

# Recruitment nodes
node((150, 410, 465, 560), "业务部门\n提出需求", "start")
node((570, 410, 920, 560), "Agent 生成\n职位画像", "agent")
diamond((1115, 485), (300, 190), "需求\n批准？")
node((1360, 410, 1675, 560), "发布职位")
node((1780, 410, 2130, 560), "Agent 简历\n筛选与匹配", "agent")
node((2235, 410, 2585, 560), "Agent 安排\n面试", "agent")
diamond((2780, 485), (300, 190), "是否\n录用？")
node((3030, 410, 3370, 560), "Agent 生成\nOffer", "agent")
node((3415, 410, 3690, 560), "进入入职\n流程", "end")
node((2640, 585, 2920, 670), "进入人才库")

# Recruitment arrows
arrow([(465, 485), (570, 485)])
arrow([(920, 485), (965, 485)])
arrow([(1265, 485), (1360, 485)], "是")
arrow([(1675, 485), (1780, 485)])
arrow([(2130, 485), (2235, 485)])
arrow([(2585, 485), (2630, 485)])
arrow([(2930, 485), (3030, 485)], "是")
arrow([(3370, 485), (3415, 485)])
arrow([(2780, 580), (2780, 585)], "否")
arrow([(1115, 580), (1115, 650), (300, 650), (300, 560)], "否", dashed=True)

# Onboarding nodes
node((155, 935, 430, 1080), "收集并\n核验资料")
node((520, 935, 800, 1080), "创建员工\n电子档案")
node((890, 935, 1170, 1080), "Agent 入职\n引导", "agent")
node((1240, 935, 1395, 1080), "入职\n完成", "end")
arrow([(430, 1007), (520, 1007)])
arrow([(800, 1007), (890, 1007)])
arrow([(1170, 1007), (1240, 1007)])

# In-service nodes
node((1585, 935, 1900, 1080), "员工或经理\n发起咨询", "input")
node((1990, 935, 2320, 1080), "Agent 政策\n知识问答", "agent")
node((2410, 935, 2750, 1080), "Agent 发起\nHR 流程", "agent")
diamond((2960, 1007), (300, 185), "需要人工\n审批？")
node((3205, 935, 3515, 1080), "HR 人工\n审核")
node((3570, 935, 3690, 1080), "结果\n反馈", "end")
arrow([(1900, 1007), (1990, 1007)])
arrow([(2320, 1007), (2410, 1007)])
arrow([(2750, 1007), (2810, 1007)])
arrow([(3110, 1007), (3205, 1007)], "是")
arrow([(3515, 1007), (3570, 1007)])
arrow([(2960, 1100), (2960, 1150), (3630, 1150), (3630, 1080)], "否", dashed=True)

# Performance nodes
node((155, 1465, 465, 1615), "制定绩效\n目标")
node((565, 1465, 910, 1615), "Agent 跟踪\n与提醒", "agent")
diamond((1120, 1540), (310, 195), "绩效\n评审")
node((1365, 1395, 1715, 1535), "Agent 生成\n发展建议", "agent")
node((1365, 1600, 1715, 1740), "制定绩效\n改进计划")
node((1815, 1465, 2170, 1615), "晋升／培养／\n持续改进")
arrow([(465, 1540), (565, 1540)])
arrow([(910, 1540), (965, 1540)])
arrow([(1275, 1505), (1320, 1505), (1320, 1465), (1365, 1465)], "达标")
arrow([(1120, 1638), (1120, 1670), (1365, 1670)], "待改进")
arrow([(1715, 1465), (1765, 1465), (1765, 1540), (1815, 1540)])
arrow([(1715, 1670), (1765, 1670), (1765, 1580), (1815, 1580)])

# Offboarding nodes
node((2385, 1465, 2670, 1615), "离职申请\n或触发", "input")
diamond((2860, 1540), (300, 195), "离职\n审批")
node((3100, 1465, 3390, 1615), "Agent 生成\n交接清单", "agent")
node((3450, 1465, 3690, 1615), "结算归档\n流程结束", "end")
arrow([(2670, 1540), (2710, 1540)])
arrow([(3010, 1540), (3100, 1540)], "通过")
arrow([(3390, 1540), (3450, 1540)])
arrow([(2860, 1638), (2860, 1745), (2525, 1745), (2525, 1615)], "退回", dashed=True)

# Cross-phase lifecycle connectors
arrow([(3550, 560), (3550, 735), (292, 735), (292, 935)], color="#246BCE", width=8)
arrow([(1395, 1007), (1485, 1007), (1485, 1007), (1585, 1007)], color="#198754", width=8)
arrow([(1318, 1080), (1318, 1235), (310, 1235), (310, 1465)], label="进入绩效周期", color="#198754", width=8)
arrow([(2170, 1540), (2265, 1540), (2265, 1540), (2385, 1540)], label="离职触发", dashed=True, color="#B46A46", width=7)

# Footer legend
legend_y = 1910
draw.text((120, legend_y), "图例", font=panel_font, fill=TEXT)
node((280, legend_y - 8, 570, legend_y + 108), "Agent 自动化", "agent")
diamond((780, legend_y + 50), (250, 125), "人工决策")
node((1000, legend_y - 8, 1290, legend_y + 108), "常规业务步骤")
draw.line((1430, legend_y + 48, 1580, legend_y + 48), fill=LINE, width=7)
draw.polygon([(1580, legend_y + 48), (1545, legend_y + 28), (1545, legend_y + 68)], fill=LINE)
draw.text((1610, legend_y + 27), "主流程", font=legend_font, fill=MUTED)

draw.line((1880, legend_y + 48, 2030, legend_y + 48), fill="#B46A46", width=6)
for x in range(1880, 2030, 28):
    draw.line((x, legend_y + 48, min(x + 16, 2030), legend_y + 48), fill=BG, width=8)
draw.polygon([(2030, legend_y + 48), (1995, legend_y + 28), (1995, legend_y + 68)], fill="#B46A46")
draw.text((2060, legend_y + 27), "条件／回退流程", font=legend_font, fill=MUTED)

draw.text(
    (120, 2072),
    "定位建议：首期 MVP 可优先实现“政策问答 + 简历筛选 + 流程发起”三个 Agent 场景",
    font=subtitle_font,
    fill=MUTED,
)

output_dir = Path("output")
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "python_hr_agent_business_flow.png"
img.save(output_path, "PNG", optimize=True)
print(output_path.resolve())
