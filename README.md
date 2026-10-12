# RepoLens

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
```

模型需要支持工具调用。`.env` 保留在本地，不提交到 Git。

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

打开 http://127.0.0.1:8000 ，输入问题并查看诊断报告。

网页当前固定分析项目自带的 `demo_repo`。
命令行入口可以指定其他仓库。

健康检查地址：http://127.0.0.1:8000/health

## 测试与评估

单元测试使用模拟模型响应，不请求真实模型：

```bash
python -B -m unittest test_report test_agent -v
```

固定案例评估会请求真实模型：

```bash
python -B evaluate.py
```

评估检查报告状态、关键证据和必要字段。
通过这些检查不等于已经证明根因判断正确。

## 输出

诊断报告包含六个字段：

- `status`：根因假设或证据不足。
- `summary`：诊断说明及检查范围。
- `evidence`：文件路径、行号和代码原文。
- `suggestion`：修复方向。
- `verification`：尚未执行的验证步骤。
- `missing_information`：继续调查需要补充的信息。

运行记录保存在 `runs/`，评估结果保存在 `eval_results/`。

## 当前边界

- 只检查工具允许访问的 Python 文件。
- 每次读取最多80行；超长请求返回第一段及续读位置。
- 每次调查最多6轮模型调用、8次工具调用。
- 读取代码并提出建议，不修改被分析的仓库，不执行其测试。
- 引用校验证明代码确实被读取；根因和修复效果仍需实际验证。