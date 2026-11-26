# Robustor

把纸面作业变成可检索的错题本：拍照上传 → 页面切分 → 书写/印刷识别 → 题目装配 → 知识点打标，最终产出错题本、统计与知识图谱。

> 当前是原型：版面与 OCR 默认走 mock provider，在设置页配置 AI Key 后可切换真实模型；识别结果始终可人工复核。

## 功能

| 页面 | 路径 | 说明 |
|---|---|---|
| 上传 | `/upload` | 批量上传试卷照片，创建处理任务 |
| 处理台 | `/console/:documentId` | 查看六个阶段的进度与日志，支持断点重跑 |
| 错题本 | `/problems` | 按状态/知识点筛选题目 |
| 题目详情 | `/problems/:problemId` | 题干、作答、批改结果、知识点标签、先修路径 |
| 知识图谱 | `/knowledge` | 11 个学科的知识点与先修关系浏览、诊断信息 |
| 统计 | `/stats` | 知识点/方法维度计数与复习计划 |
| 设置 | `/settings` | AI Provider（Base URL / 模型 / Key 密文存储）与配置测试 |

## 技术栈

- 后端：FastAPI + SQLAlchemy 2 + SQLite（`apps/api`）
- 前端：React 18 + Vite + TanStack Query（`apps/web`）
- 没有 alembic：启动时执行 `PRAGMA table_info` 检查并按需 `ALTER TABLE`，配合幂等种子与图谱导入

## 快速开始

```bash
make install      # 建 venv、装后端与前端依赖
make seed         # 可选：写入演示数据
make dev          # API → http://localhost:8888/api/docs，Web → http://localhost:5173
make serve        # 单端口模式：构建前端后由 FastAPI 一起托管（默认 8888）
make test         # 后端 pytest + 前端 vitest
```

环境变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `RB_PORT` | `8888` | API / 单端口端口 |
| `RB_DATA_DIR` | `./data` | SQLite 与上传文件目录 |
| `RB_TAXONOMY_DIR` | `./taxonomy` | 知识图谱数据目录 |

AI Key 也可以只走环境变量（`VLM_*`）；数据库中的配置优先，页面保存后下一个任务即生效。

## 处理流水线

`apps/api/app/pipeline/orchestrator.py` 按顺序串起六个阶段，每个阶段可单独重跑：

| 阶段 | 作用 | 粒度 |
|---|---|---|
| `preprocess` | 缩放、去噪、方向校正 | 页 |
| `layout` | 版面切分与区域分类（题干 / 作答 / 批改） | 页 |
| `ink` | 区分打印字与手写笔迹 | 页 |
| `recognize` | OCR（mock 或 VLM） | 页 |
| `assemble` | 装配题目、作答与批改，写入 `problem` / `solution` / `mark` | 文档 |
| `tag` | 知识点自动打标 | 文档（幂等） |

## 知识图谱

- 数据位于 `taxonomy/`，启动时由 `app.taxonomy.import_taxonomy()` 幂等导入：**4221 个知识点 / 6681 条先修边 / 11 个学科**（数学 870、语文 827、英语 791……）。
- 知识点落为 `Tag(type="knowledge")`，先修关系落为 `TagEdge(from=前置, to=后继, strength=hard|soft)`。
- 展示名重复时按「学科 / 学段 / 章节 / external_id」自动加后缀，`(type, normalized_name)` 唯一约束保持有效。
- 接口：`GET /api/taxonomy/summary`、`/api/taxonomy/topics`、`/api/taxonomy/topics/{tag_id}`、`/api/taxonomy/problems/{problem_id}/path`。
- 页面：`/knowledge`，支持学科切换、章节筛选、诊断题浏览。

## 知识点自动打标

`apps/api/app/pipeline/s6_tag.py` 叠加两条路径，按标签去重并取较高权重：

1. **本地词表（始终执行）**：题干/解答中出现的 approved 标签名直接命中；中文短语做模糊对齐后挂 `weight=0.6`。
2. **LLM 语义打标（配置了 Key 才执行）**：用字符 bigram 召回 40 个候选知识点，模型只能从候选里选并给出置信度（`<0.55` 丢弃）。编造的名称只计数、不建标签，避免污染词表。

匹配不上的短语会写成 `Tag(status="pending")` 进入审核队列，不会直接成为 approved 标签。

## 错题诊断（设计稿，未实现）

知识点与方法的双层诊断框架见 [docs/error-diagnosis-framework.md](docs/error-diagnosis-framework.md)：以「知识图 × 方法图」上的最近失败节点定位错因，输出主因、证据引用与补学路径。方法论图谱目前只有 20 个扁平标签，需先补齐依赖与适用条件。

## 目录结构

```
apps/api/     FastAPI 应用、流水线、测试
apps/web/     React 前端
data/         运行时数据（SQLite、上传与页面图，不入库）
docs/         设计文档
scripts/      开发与演示脚本
taxonomy/     知识图谱数据（来自第三方，CC BY-NC 4.0，见下）
```

## 许可与第三方引用

- 本仓库**代码**以 MIT 许可发布，见 [LICENSE](LICENSE)。
- `taxonomy/` 目录下的知识点与先修边数据来自 [cn-math-taxonomy](https://github.com/xiaoyang111222/cn-math-taxonomy)，采用 **CC BY-NC 4.0（署名-非商业性使用）**，许可证全文见 `taxonomy/LICENSE`。
- 因此**整个仓库不能直接用于商业产品或商业服务**。如需商用，请删除 `taxonomy/` 目录并替换为自建或已获商业授权的数据。
- 主要运行时依赖及其许可、数据的修改说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
- 模型中转服务（如火山方舟等 OpenAI 兼容接口）由使用者自行配置，遵循对应服务商条款，本仓库不包含任何模型权重。
