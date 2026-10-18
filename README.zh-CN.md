# RepoLens

[English](README.md) | 简体中文

一个用于诊断本地 Python 仓库问题的 AI Agent。

输入仓库路径和问题描述，Agent 自主选择搜索关键词、读取代码，
输出根因假设、代码证据、修复建议和验证步骤。

## 已实现

- 文件列表、关键词搜索、带行号的代码读取工具。
- 模型自主选择工具的调查循环。
- 结构化 JSON 诊断报告。
- 引用校验：证据必须来自本次实际读取的代码，并与原文一致。
- 模型调用次数、工具调用次数和单次读取行数限制。
- 命令行入口、网页演示、单元测试和固定案例评估。
- 保存调查过程和最终报告。
- 运行记录同时保存到 JSON 文件和 PostgreSQL（`runs` 与 `evidence` 表）。
- REST API（`/api/runs`）：创建、列出、查询和删除运行记录，包含输入校验、API 密钥角色和基于 PostgreSQL 的集成测试。

核心流程：

问题 → 模型选择工具 → 执行工具 → 返回结果 → 继续调查 → 校验报告

## 安装

开发环境为 Python 3.13.9。以下命令适用于 macOS/Linux，
请在项目根目录执行：

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

在项目根目录创建 `.env`，将占位值替换为你的服务商配置：

```dotenv
LLM_MODEL_ID=你的模型名称
LLM_API_KEY=你的API密钥
LLM_BASE_URL=你的OpenAI兼容API地址
LLM_TIMEOUT=60
# LLM_REASONING_EFFORT=none
REPOLENS_USER_KEY=你的用户密钥
REPOLENS_ADMIN_KEY=你的管理员密钥
```

模型需要支持工具调用。`.env` 保留在本地，不提交到 Git。
`LLM_REASONING_EFFORT` 可选，只有服务商支持 `reasoning_effort` 参数时才设置；不设置时不发送该参数。

两个 `REPOLENS_*_KEY` 用于保护 REST API：用户密钥可以创建诊断，管理员密钥还可以删除记录。
用下面的命令分别生成两个密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 数据库（PostgreSQL）

每次运行也会保存到 PostgreSQL。数据库未启动时，命令行运行仍会完成，只保存到 `runs/`。
网页演示和 REST API 依赖数据库，数据库不可用时返回 `503`。

在 macOS 上安装并启动 PostgreSQL：

```bash
brew install postgresql@18
brew services start postgresql@18
echo 'export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
createdb repolens
```

建表并导入已有运行记录（可重复执行）：

```bash
python -B db.py
```

默认连接 `dbname=repolens`，可通过 `DATABASE_URL` 指定其他数据库。

数据表：

- `runs`：每次诊断一行，完整报告和调查轨迹以 JSONB 保存。
- `evidence`：每条证据一行，通过外键关联 `runs`。

示例查询：

```bash
psql repolens -e -f sql/step6_queries.sql
```

## 命令行诊断

```bash
python -B diagnose.py demo_repo \
  "要求订单金额大于等于50元免运费，但金额正好50元时仍收取8元，请定位原因并提供代码证据。"
```

第一个参数是仓库目录，第二个参数是问题描述。
更换这两个参数即可诊断其他本地 Python 仓库。

查看帮助：

```bash
python -B diagnose.py --help
```

## 网页演示

```bash
python -m uvicorn server:app --reload --port 8000
```

打开 http://127.0.0.1:8000 ，输入问题和用户密钥，查看诊断报告。
展开“Tool calls”可查看每次工具调用的参数和返回结果；诊断失败时页面显示失败原因。

网页当前固定分析项目自带的 `demo_repo`。
命令行入口可以指定其他仓库。

健康检查地址：http://127.0.0.1:8000/health

## REST API

网页演示的服务同时提供诊断记录的 REST API。
交互式文档：http://127.0.0.1:8000/docs （点击 **Authorize** 输入密钥）。

| 方法 | 路径 | 需要的密钥 | 成功 | 错误 |
|---|---|---|---|---|
| `POST` | `/api/runs` | 用户或管理员 | `201`，带 `Location` 响应头 | `401`、`422`、`503` |
| `GET` | `/api/runs` | 无 | `200` | `422`、`503` |
| `GET` | `/api/runs/{id}` | 无 | `200` | `404`、`422`、`503` |
| `DELETE` | `/api/runs/{id}` | 管理员 | `204` | `401`、`403`、`404`、`503` |

- 密钥放在 `X-API-Key` 请求头中。
- `POST` 接收 `{"question": "..."}`（1–4000 个字符，不允许其他字段），用真实模型诊断 `demo_repo`，返回保存后的运行记录。
- `GET /api/runs` 按时间倒序返回运行记录。`limit` 取 1–100（默认 10）；`status` 取 `hypothesis` 或 `insufficient_evidence`。

错误码：

- `401`：缺少密钥或密钥无效。
- `403`：密钥有效但没有权限（删除需要管理员密钥）。
- `404`：不存在该 id 的运行记录。
- `422`：输入不合法，响应中会指出出错的字段和规则。
- `503`：数据库不可用。

示例：

```bash
export $(grep '^REPOLENS_' .env | xargs)
curl -s 'http://127.0.0.1:8000/api/runs?limit=5&status=hypothesis'
curl -s http://127.0.0.1:8000/api/runs/1
curl -i -X POST http://127.0.0.1:8000/api/runs \
  -H "X-API-Key: $REPOLENS_USER_KEY" -H "Content-Type: application/json" \
  -d '{"question": "要求订单金额大于等于50元免运费，但金额正好50元时仍收取8元。"}'
curl -i -X DELETE http://127.0.0.1:8000/api/runs/1 -H "X-API-Key: $REPOLENS_ADMIN_KEY"
```

## 测试与评估

单元测试使用模拟模型响应，不请求真实模型。
API 集成测试向应用发送真实的 HTTP 请求，并使用单独的 `repolens_test` 数据库，每个测试开始前会清空该库：

```bash
createdb repolens_test
python -B -m unittest test_tools test_report test_agent test_api -v
```

固定案例评估会请求真实模型：

```bash
python -B evaluate.py
```

评估检查报告状态、关键证据和必要字段。
通过这些检查不等于已经证明根因判断正确。

## 输出

诊断报告包含七个字段：

- `status`：根因假设或证据不足。
- `summary`：诊断说明及检查范围。
- `root_cause`：由证据推断出的根因假设，证据不足时为空。
- `evidence`：文件路径、行号和代码原文。
- `suggestion`：修复方向。
- `verification`：尚未执行的验证步骤。
- `missing_information`：继续调查需要补充的信息。

运行记录保存在 `runs/` 和 PostgreSQL 的 `runs` 表，评估结果保存在 `eval_results/`。
评估结果中每个用例都记录了对应的运行记录文件、模型、调用次数和耗时。

## 当前边界

- 只检查工具允许访问的 Python 文件。
- 每次读取最多80行；超长请求返回第一段及续读位置。
- 每次调查最多6轮模型调用、8次工具调用。
- 报告校验不合格时，错误会反馈给模型修正；重试计入6轮模型调用上限。
- 读取代码并提出建议，不修改被分析的仓库，不执行其测试。
- 引用校验证明代码确实被读取；根因和修复效果仍需实际验证。
- API 密钥是 `.env` 中的固定值，没有用户账号和登录会话。
- `POST /api/runs` 要等整个诊断完成后才返回响应。
