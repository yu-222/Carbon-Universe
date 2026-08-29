# 🌍 Carbon Universe · 碳宇

> 一站式虚拟碳中和平台 —— 覆盖「AI 碳核算 → 碳资产交易 → 碳普惠激励 → 凭证台账」完整闭环。

黑客松 MVP 项目，前端纯单文件 Vue3（CDN，无需构建），后端 FastAPI，数据用内存字典 + JSON 文件持久化，**双击 + 一条命令即可运行**。

---

## ✨ 核心功能

| 模块 | 说明 |
|---|---|
| 🏠 **首页概览** | 项目介绍 + 三张实时数据卡（总核算次数、总交易量、总积分） |
| 🤖 **AI 智能碳核算** | 支持「表单输入」与「自然语言输入」两种模式，模拟大模型估算碳排放、生成明细与减碳建议 |
| 💹 **虚拟碳资产交易所** | 碳信用 + 法币双余额，挂买/卖单、点击对手方订单吃单成交，双方余额结算、订单移除、成交记录 |
| 🎁 **碳普惠激励系统** | 打卡减碳行为得积分（步行通勤、关灯、自带水杯等）、积分变动记录、积分抵扣 |
| 📄 **凭证台账导出** | 汇总用户信息 / 碳核算 / 交易 / 积分，一键 `window.print()` 导出 PDF |

---

## 🛠 技术栈

- **前端**：Vue3（CDN 引入，单文件 `index.html`，无需构建工具）
- **后端**：Python FastAPI + Uvicorn
- **存储**：内存字典 + JSON 文件持久化（无数据库）
- **大模型**：OpenAI 兼容 Chat Completions 接口（API Key 由你提供），未配置时自动降级为确定性规则解析

---

## 📁 项目结构

```
carbon-universe/
├── backend/
│   ├── main.py              # FastAPI 入口：CORS、路由注册
│   ├── bootstrap.py         # 仓库注册与数据存储初始化
│   ├── agents/              # AI 碳核算 Agent 包
│   │   ├── orchestrator.py      # 编排步骤、状态、重试与最终输出
│   │   ├── activity_parser.py   # 自然语言 → 结构化活动项
│   │   ├── factor_selector.py   # 按地区/行业/年份/单位选择因子
│   │   ├── calculation.py       # 确定性公式 amount × factor
│   │   ├── verification_agent.py# 缺失项/单位/异常值/适用范围/低置信
│   │   ├── recommendation_agent.py # 按主要排放项生成减排建议
│   │   ├── ledger_writer.py     # 原子保存报告、明细、因子版本与轨迹
│   │   └── llm.py               # OpenAI 兼容 LLM 客户端（.env 配置）
│   ├── schemas/             # Pydantic 模型（CarbonReport / EmissionLedger 等）
│   ├── routes/carbon.py     # 核算 Agent 接口
│   ├── data/
│   │   ├── emission_factors.json # 排放因子库（ID/版本/来源/适用范围）
│   │   └── *.json                # 运行后生成的持久化数据
│   ├── .env.example         # LLM 配置示例（复制为 .env）
│   └── requirements.txt
└── frontend/
    └── carbon-universe.html # 单文件 Vue3 应用（CDN）
```

---

## 🚀 快速启动

### 1. 启动后端

```bash
cd carbon-universe/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

启动成功后：
- API 地址：<http://localhost:8000>
- 交互式文档（Swagger）：<http://localhost:8000/docs>
- 首次启动会自动填充演示数据（2 个用户、1 份报告、若干挂单与积分记录）

### 2. 配置大模型（可选，推荐）

AI 碳核算 Agent 的解析与建议走 OpenAI 兼容接口。**API Key 由你提供**，配置方式：

```bash
cd backend
cp .env.example .env
# 编辑 .env，填入你的密钥 / 网关地址 / 模型名
```

```ini
LLM_API_KEY=sk-你的密钥
LLM_BASE_URL=https://api.openai.com/v1    # 或兼容网关，如 DeepSeek / 通义 / Moonshot
LLM_MODEL=gpt-4o-mini
```

- 兼容任何 Chat Completions 协议的提供商（OpenAI / DeepSeek / 通义千问 / Moonshot 等）
- 也可用 `OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL` 环境变量
- **未配置时核算链路自动降级为确定性规则解析**，接口依然完整可用（仅 `model_name` 显示 `rule-based`）

### 3. 打开前端

直接**双击 `frontend/index.html`**，或用浏览器打开即可。前端默认请求 `http://localhost:8000`，后端已开启全局 CORS。

> 💡 若想重置演示数据：删除 `backend/data.json` 后重启后端即可。

---

## 📡 API 一览

所有接口前缀 `http://localhost:8000`，错误统一返回 `{"error": "描述"}`。

### 通用
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/overview` | 首页数据概览 |
| GET / POST | `/api/users` | 用户列表 / 创建用户 |

### AI 碳核算 Agent `/api/carbon`
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/calculate` | 提交核算（`mode: form / nl`），走 Agent 流水线 |
| GET | `/reports` | 历史报告列表 |
| GET | `/reports/{id}` | 单份报告（含 Agent 轨迹） |
| GET | `/reports/{id}/ledger` | 报告的全流程台账（因子快照/公式/轨迹/校验哈希） |
| GET | `/ledgers` | 全流程台账列表（审计追溯） |
| GET | `/factors` | 排放因子库（ID/数值/版本/来源/适用范围） |

核算流水线：`Activity Parser → Factor Selector → Calculation → Verification → Recommendation → Ledger Writer`，首版一次 LLM 调用完成解析与建议。

### 交易所 `/api/exchange`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/balance` | 碳信用 + 法币余额 |
| GET | `/orders` | 订单簿（买/卖分开，价格优先） |
| POST | `/orders` | 挂单（`type: buy/sell, amount, price`） |
| POST | `/match` | 吃单成交（`order_id`） |
| GET | `/trades` | 成交历史 |

### 碳普惠 `/api/points`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/balance` | 积分余额 |
| GET | `/behaviors` | 可打卡行为列表 |
| POST | `/checkin` | 打卡（`behavior`） |
| GET | `/history` | 积分变动记录 |
| POST | `/redeem` | 积分抵扣（`points`） |

### 导出 `/api/export`
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/summary` | 台账汇总数据 |
| GET | `/report/{id}.csv` / `.json` | 单报告导出 |

---

## 🎬 3 分钟演示脚本

1. **首页** — 打开页面，展示项目介绍与三张数据概览卡（核算次数 / 交易量 / 积分）。
2. **AI 碳核算** — 切到「碳核算」，用自然语言输入：
   > `今年上半年，我在北京开车通勤约 800 公里，办公室用电 3000 度，食堂天然气用了 200 立方米`

   点击「AI 核算」，展示自动识别的分项排放、总排放与减碳建议。
3. **交易所** — 切到「交易所」，展示资产余额；在订单簿中点击「低碳出行者」的挂单**吃单成交**，成交后余额变动、订单消失、成交历史新增一条。
4. **碳普惠** — 切到「碳普惠」，点击「步行通勤 +50」打卡，积分实时增加；再输入数值「积分抵扣」，演示扣减。
5. **导出台账** — 切到「导出」，展示用户/核算/交易/积分四块汇总，点击「🖨 导出 PDF」调起打印（可另存 PDF）。

---

## 📝 说明与后续可扩展

- **核算链路**：LLM 负责解析与建议，排放数值一律由 `calculation.py` 确定性计算（`amount × factor`），绝不由大模型心算。
- **全流程可追溯**：每份报告自动记录原始输入、结构化活动项、因子 ID/版本/来源/适用范围、公式、模型名、Prompt 版本、工具调用、耗时、状态、置信度、校验警告、报告版本与 SHA-256 校验哈希。
- 交易所吃单为**全额成交**（点一次吃掉整张对手单），未做部分成交/自动撮合，符合 MVP 优先跑通闭环的目标。
- 可扩展方向：多轮 Agent 对话、因子库在线更新、成交后自动发放碳普惠积分打通四模块联动、多用户切换、部分成交撮合。

---

**Carbon Universe · 碳宇** — 让每一份碳足迹都可核算、可交易、可激励、可追溯。🌱
