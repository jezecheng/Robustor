"""种子数据：默认墨迹方案 + 60 个数学标签（40 knowledge / 20 method）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import InkProfile, Tag
from .textutil import normalize_name

KNOWLEDGE = [
    "一元二次方程", "因式分解", "配方法", "求根公式", "判别式", "韦达定理", "二次函数", "抛物线",
    "顶点式", "对称轴", "一次函数", "反比例函数", "勾股定理", "相似三角形", "全等三角形", "三角形面积",
    "圆的切线", "圆周角", "平行四边形", "矩形", "菱形", "梯形", "三角函数", "正弦定理",
    "余弦定理", "等差数列", "等比数列", "不等式", "绝对值", "分式方程", "根式", "指数函数",
    "对数函数", "概率初步", "统计初步", "平面直角坐标系", "图形变换", "动点问题", "立体几何", "函数图象",
]

METHODS = [
    "因式分解法", "配方法解方程", "公式法", "换元法", "待定系数法", "数形结合", "分类讨论", "构造函数",
    "辅助线", "面积法", "比例法", "判别式分析", "排除法", "特殊值法", "整体代换", "消元法",
    "降次法", "建模法", "图像法", "逆推法",
]

DEFAULT_RULES = {
    "name": "默认（黑解答/红批改/蓝订正）",
    "roles": [
        {"role": "print", "color": "black", "mode": "printed", "sat_max": 40},
        {"role": "answer", "color": "black", "mode": "handwritten", "sat_max": 40},
        {"role": "mark", "color": "red", "hue": [-15, 20], "sat_min": 80,
         "shapes": ["cross", "tick", "circle", "underline", "score"]},
        {"role": "correction", "color": "blue", "hue": [200, 255], "sat_min": 70},
    ],
    "page_overrides": {},
}


def seed_all(session: Session | None = None) -> dict:
    own = session is None
    if own:
        init_db()
    db = session or SessionLocal()
    created = {"ink_profiles": 0, "tags": 0}
    try:
        if db.query(InkProfile).count() == 0:
            db.add(InkProfile(name=DEFAULT_RULES["name"], is_default=True, rules_json=DEFAULT_RULES))
            created["ink_profiles"] += 1

        existing = {row[0] for row in db.query(Tag.normalized_name).all()}
        for tag_type, names in (("knowledge", KNOWLEDGE), ("method", METHODS)):
            for name in names:
                key = normalize_name(name)
                if key in existing:
                    continue
                db.add(Tag(type=tag_type, name=name, normalized_name=key, status="approved"))
                existing.add(key)
                created["tags"] += 1
        db.commit()
    finally:
        if own:
            db.close()
    return created
