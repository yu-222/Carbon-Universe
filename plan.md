# Carbon Universe 核心功能与架构建议

目标主线：`全球观察 → AI 核算 → 减碳行动/碳交易 → 可信记录`。首版只保留能形成闭环的功能。

## 1. 四个核心模块

1. **全球碳观测**：一张地图切换查看实际排放源与全球碳价。
2. **AI 碳核算 Agent**：理解自然语言或表单，生成可复核的排放报告。
3. **个人碳行动与资产**：记录行为、减排量、积分、碳信用和模拟交易。
4. **可信记录**：保存核算依据、Agent 过程、行为凭证和交易流水。

## 2. 全球碳观测

只做一个地图容器，通过顶部按钮切换两种数据：

| 图层 | 参考数据 | 首版重点 |
|---|---|---|
| 碳追踪 | Climate TRACE | 电厂、钢厂、油田等项目点位、行业与排放量 |
| 碳价格 | World Bank、ICAP | ETS/Carbon Tax、$/tCO₂、覆盖率与价格曲线 |

交互建议：

- 地图顶部只放“碳追踪 / 碳价格”双选切换，不跳转新页面；
- 碳追踪支持国家、年份和行业筛选，点位展示项目级排放详情；
- 碳价格支持市场、年份和机制筛选，国家或区域着色展示当前价格；
- 两种模式共用搜索、时间轴、图例和详情卡；
- 地图、价格曲线、排行榜联动；
- 每条数据展示来源、统计周期、发布时间和最后同步时间；
- 碳价可按日/周更新，排放源按来源支持的项目级周期更新；
- 首版读取本地 JSON 快照，不在前端直接请求外部平台。

视觉演示可使用 **Google 3D 地图/3D 地球底图**：碳追踪模式用发光点、柱体高度和热力颜色表现排放规模；碳价格模式用国家或区域色阶表现价格。首版重点是演示效果，数据交互仍由同一个地图组件承担，并保留普通 2D 底图作为降级方案。

## 3. AI 碳核算 Agent

### 3.1 核算链路

大模型负责理解和解释，排放数值必须由确定性计算服务完成：

```text
用户输入
  → Orchestrator Agent
  → Activity Parser：提取活动、数量、单位、地区和时间
  → Factor Selector：匹配排放因子及版本
  → Calculation Service：amount × factor
  → Verification Agent：检查缺失项、单位、异常值和适用范围
  → Recommendation Agent：生成减排建议
  → Ledger Writer：保存报告与全流程记录
```

首版只需一次 LLM 调用完成解析和建议；Agent 先体现为明确的代码职责，不必拆成多次模型对话。

### 3.2 Agent 职责

| 文件 | 职责 |
|---|---|
| `orchestrator.py` | 编排步骤、状态、重试和最终输出 |
| `activity_parser.py` | 将自然语言转为结构化活动项 |
| `factor_selector.py` | 按地区、行业、年份和单位选择因子 |
| `verification_agent.py` | 检查缺失字段、冲突、异常值和低置信结果 |
| `recommendation_agent.py` | 根据主要排放项给出可执行建议 |
| `calculation.py` | 执行确定性公式，不依赖 LLM 心算 |
| `ledger_writer.py` | 原子保存报告、明细、因子版本和 Agent 轨迹 |

### 3.3 必须记录

- 原始输入、输入类型和结构化活动项；
- 数量、单位、地区、时间和核算边界；
- 排放因子 ID、数值、版本、来源和适用范围；
- 计算公式、分项排放、总排放和结果单位；
- 模型名称、Prompt 版本、工具调用、耗时和状态；
- 置信度、校验警告、人工修改、报告版本和校验哈希。

## 4. 数据存储建议

当前阶段只使用本地 JSON，先把数据结构和读写接口稳定下来；后续需要多人使用、并发写入和复杂查询时，再迁移到 SQL 数据库。业务层只调用 Repository，不直接读写文件，确保以后替换 SQL 不必重写 Agent 和 API。

### 4.1 JSON 文件

```text
users.json                 用户与组织主体
emission_factors.json      排放因子、版本、来源和适用范围
calculation_jobs.json      核算任务、结构化活动项和状态
calculation_reports.json   分项结果、总量、版本和校验哈希
agent_runs.json            模型、Prompt、工具轨迹、耗时和错误
behavior_records.json      个人低碳行为、凭证和估算减排量
points_ledger.json         积分增减流水
trades.json                挂单与成交记录
emission_assets.json       碳追踪点位和项目排放数据
carbon_prices.json         ETS/Carbon Tax 及价格时间序列
sync_runs.json             数据来源、更新时间和同步记录
audit_logs.json            关键数据修改审计
```

每条记录使用稳定 ID，并保存 `created_at`、`updated_at` 和 `schema_version`。核算报告不能只存总量，必须关联明细、因子版本和 Agent 记录；积分、交易、核算与行为采用追加记录，不直接覆盖历史值。写入时使用临时文件替换，避免中途失败损坏 JSON。

### 4.2 SQL 演进目标

未来可将同名 JSON 集合迁移为 SQL 表，优先采用 SQLite/PostgreSQL + SQLAlchemy + Alembic。当前只预留 Repository 接口和稳定字段，不安装数据库依赖，也不实现迁移脚本。

## 5. 推荐工程目录

```text
backend/
├── app/
│   ├── main.py
│   ├── core/                    # config、logging、security
│   ├── api/routes/
│   │   ├── carbon.py
│   │   ├── observatory.py
│   │   ├── market.py
│   │   ├── behaviors.py
│   │   └── ledger.py
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── activity_parser.py
│   │   ├── factor_selector.py
│   │   ├── verification_agent.py
│   │   ├── recommendation_agent.py
│   │   └── prompts/
│   ├── services/
│   │   ├── calculation.py
│   │   ├── emission_factors.py
│   │   ├── ledger_writer.py
│   │   ├── observatory.py
│   │   ├── market.py
│   │   └── data_sync.py
│   ├── repositories/
│   │   ├── json_repository.py
│   │   └── interfaces.py       # 后续可增加 SQL 实现
│   ├── schemas/
│   └── jobs/sync_external_data.py
├── data/
│   ├── emission_assets.json
│   ├── carbon_prices.json
│   ├── emission_factors.json
│   ├── calculations/
│   └── ledgers/
└── tests/{agents,services,api,repositories}/
```

边界建议：`agents` 负责语言理解与编排，`services` 负责业务规则，`repositories` 负责 JSON 读写并预留 SQL 替换能力；API 路由不直接操作文件，也不直接请求外部数据源。

## 6. 最小接口

```text
POST /api/carbon/calculations
GET  /api/carbon/calculations/{id}
GET  /api/carbon/reports
GET  /api/observatory/layers/{layer}
GET  /api/observatory/items/{id}
GET  /api/pricing/markets/{id}/series
POST /api/behaviors/checkins
GET  /api/ledger/audit/{record_id}
```

## 7. 今日开发优先级

1. 定义本地 JSON Schema 和统一 Repository 读写接口。
2. 跑通 `Orchestrator → Parser → Factor → Calculation → Verification → Ledger`。
3. 让一次自然语言核算生成报告、明细、Agent 轨迹和审计记录。
4. 准备碳追踪与碳价格两份地图 JSON 数据。
5. 完成一个地图组件、双模式切换和 Google 3D 地图演示。

今日不做：SQL 数据库实现、CCUS/CDR 图层、自治多 Agent、向量数据库、全量实时抓取、复杂撮合和区块链合约。README 应补充 Agent 流程、JSON 数据结构、目标目录、地图双模式、数据来源与更新规则，以及未来迁移 SQL 的路径。
