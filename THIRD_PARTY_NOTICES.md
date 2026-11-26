# 第三方作品与依赖声明

本文件列出随仓库分发的外部数据、主要运行时依赖及其许可。代码依赖的完整清单以 `apps/api/pyproject.toml`、`apps/web/package.json` 和 `package-lock.json` 为准，各依赖保留其原始许可与版权声明。

## 1. 数据集：cn-math-taxonomy（重要）

| 项 | 内容 |
|---|---|
| 作品 | cn-math-taxonomy（中国中小学知识点与先修关系） |
| 来源 | https://github.com/xiaoyang111222/cn-math-taxonomy |
| 引用版本 | commit `4e87079b378236e282cde238ef1dcd9f211eb9f5` |
| 许可 | **CC BY-NC 4.0**（Attribution-NonCommercial 4.0 International） |
| 许可全文 | [`taxonomy/LICENSE`](taxonomy/LICENSE)；官方文本 https://creativecommons.org/licenses/by-nc/4.0/ |
| 使用位置 | `taxonomy/topics.json`、`taxonomy/dependencies.json`、`taxonomy/meta.json` |

**对本仓库的修改**（CC BY-NC 4.0 要求标注改动）：

- 将上游按学科分散的数据汇总为两个 JSON 文件，保留知识点与先修边的内容语义，不改变条目含义。
- 为数学学科补充 `subject` 字段；各学科的知识点与边按上游原样裁剪，统计信息写入 `taxonomy/meta.json`。
- 导入数据库时对重名知识点追加「学科 / 学段 / 章节 / external_id」后缀，仅为满足 `(type, normalized_name)` 唯一约束，不改变上游数据文件。

**许可义务与限制**：

1. **署名**：再分发或公开展示时必须保留上述来源、作者与许可说明。
2. **非商业性使用**：不得将本数据集用于商业目的（包括商业产品、付费服务、以营利为目的的内部系统）。该限制覆盖包含该数据的整体分发物。
3. **不得附加额外限制**：不得对数据集再许可或施加与 CC BY-NC 4.0 冲突的条款。
4. **无担保**：数据按「现状」提供，不附带任何明示或默示担保。
5. CC BY-NC 4.0 不授予商标权或专利权。

> 结论：本仓库的**代码**是 MIT，但 `taxonomy/` 数据是 CC BY-NC 4.0，两者不冲突，只是整体分发**不能商用**。商用前请移除 `taxonomy/` 并替换为自建或已获商业授权的数据，同时删除 `RB_TAXONOMY_DIR` 相关导入即可（导入逻辑在数据目录缺失时会跳过）。

## 2. 主要运行时依赖

| 依赖 | 许可 | 用途 |
|---|---|---|
| FastAPI | MIT | HTTP API |
| Uvicorn | BSD-3-Clause | ASGI 服务器 |
| SQLAlchemy | MIT | ORM |
| Pydantic | MIT | 数据校验 |
| HTTPX | BSD-3-Clause | 模型服务调用 |
| Pillow | MIT-CMU（HPND） | 图像处理 |
| NumPy | BSD-3-Clause | 数值计算 |
| opencv-python-headless | MIT（内含 OpenCV，Apache-2.0） | 版面与图像预处理 |
| cryptography | Apache-2.0 OR BSD-3-Clause | API Key 加密存储 |
| React / React DOM | MIT | 前端框架 |
| React Router | MIT | 前端路由 |
| TanStack Query | MIT | 数据请求与缓存 |
| KaTeX | MIT | 公式渲染 |
| Vite | MIT | 前端构建 |
| TypeScript | Apache-2.0 | 类型检查 |
| Vitest / MSW | MIT | 前端测试与接口 mock |
| openapi-typescript | MIT | 由 OpenAPI 生成类型 |

## 3. 外部服务

- 模型服务（如火山方舟、OpenAI 或其他 OpenAI 兼容接口）不随仓库分发，Key 由使用者自行配置并以密文保存在本地数据库。
- 模型输出仅用于辅助打标与展示，可能存在错误；使用者需自行确认其合规性与准确性。

## 4. 商标

文中出现的第三方名称与商标归其各自所有者，仅用于说明来源与兼容性。
