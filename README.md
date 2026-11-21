# S3-MATCH-031 · 撮合商机 opportunity 模型与迁移

ClawHunt 工单 **#2056**（会员空间平台 · Stage iii 业务框架与小程序 · 模块：供需、匹配与商机）交付候选。

公开仓库：<https://github.com/PikachuGits/s3-match-031-opportunity-models>（默认分支 `main`，可匿名读取）

本单建立**撮合商机 `opportunity`** 与两张配套表：`opportunity_meeting`（线下对接记录）、
`opportunity_stage_log`（阶段留痕），并与招商商机 `deal` **分表**。交付物为模型代码、
Alembic 迁移、单元测试与本文档（含五阶段与三类对象的关系图）。

- 数据库：PostgreSQL **16.16**（实测版本，见 `evidence/environment.txt`）
- 运行时：Python **3.12.13**（要求 3.11+）
- 测试：**149 passed**（真实 PostgreSQL，见 `evidence/test-results.txt`）
- 迁移：`upgrade → downgrade → upgrade` 全部成功，`alembic check` 零漂移（见 `evidence/migration-check.txt`）

> **边界声明（先读）**
>
> 1. 本单只交**数据模型、迁移、单元测试与文档**。HTTP 接口、工作台前端、小程序、商机创建前的
>    需求发布与 AI 匹配算法均不在本单范围；`app/services/` 提供可直接被接口层调用的领域服务。
> 2. **`opportunity` 与招商商机 `deal` 是两张独立的表**，本仓库未建 `deal` 表，也未与其共享字段或外键，
>    避免两个工单互相耦合。
> 3. S2-CRM 按工单允许的方式用**接口桩**先行：企业、员工、需求条目、匹配记录、对接请求与活动只存
>    UUID 引用，**不建跨模块外键**（见 §8）。生产接入时由 S2-CRM 保证被引用对象存在。
> 4. 全部数据为虚构 UUID 与虚构文案，不含客户名称、真实企业或个人信息。
> 5. 不引入任何向境外发送数据的第三方 SDK；连接串与配置只从环境变量读取。

---

## 1. 范围

| 做 | 不做 |
|---|---|
| `opportunity` 模型与迁移（全部字段、CHECK、索引） | 需求发布 / AI 匹配算法 / 打分因子 |
| `opportunity_meeting` 模型与迁移（三种类型、参与方、纪要、活动） | 工作台页面、小程序页面、消息通知 |
| `opportunity_stage_log` 模型与迁移（from / to / 操作人 / 原因 / 时间） | 招商商机 `deal` 表与合同、回款字段 |
| 阶段状态机、结果写入、关闭规则（服务层） | 定时任务、报表、告警、归档 |
| 单元测试 149 项（真实 PostgreSQL） | 真实 S2-CRM 联调、SSO、网关路由 |

---

## 2. 五阶段与三类对象

五阶段中 **① 需求发布** 与 **② AI 匹配** 的操作对象分别是**供需条目**与**匹配记录**；
撮合商机在 ② 被采纳（或对接请求被受理、员工人工引荐、活动现场发起）时**创建并进入 ③**。

```mermaid
flowchart LR
    subgraph S12["①② 之前的对象（他单负责）"]
        A["① 需求发布<br/>supply / demand item"]
        B["② AI 匹配<br/>match 记录"]
        Q["对接请求<br/>connect_request"]
        EV["活动<br/>event"]
    end

    A --> B
    B -->|"匹配被采纳<br/>origin=ai_match"| C
    Q -->|"请求被受理<br/>origin=member_initiated"| C
    S["员工人工引荐<br/>origin=staff_intro"] --> C
    EV -->|"现场发起<br/>origin=event"| C

    C["③ 员工跟进<br/>stage=follow_up"]
    C --> D["④ 线下对接<br/>stage=meeting"]
    D --> F["⑤ 成交记录<br/>stage=outcome"]
    F --> G["closed<br/>终态"]

    C -. "每场对接写一条" .-> M[("opportunity_meeting")]
    D -. "每场对接写一条" .-> M
    C -. "每次流转写一条" .-> L[("opportunity_stage_log")]
    D -. "每次流转写一条" .-> L
    F -. "每次流转写一条" .-> L
    G -. "每次流转写一条" .-> L
```

**三类对象的关系**

| 对象 | 所在阶段 | 表 | 与商机的关系 |
|---|---|---|---|
| 供需条目（需求 / 供给 item） | ① 需求发布 | 他单（S3-MATCH 其他工单） | `opportunity.source_item_id` 引用；员工人工引荐时可为空 |
| 匹配记录 | ② AI 匹配 | 他单 | `opportunity.match_id` 引用；`origin=ai_match` 时必填 |
| 撮合商机 | ③–⑤ | `opportunity` | 本单主体；`opportunity_meeting` 与 `opportunity_stage_log` 挂在它下面 |

ER 图见 [`docs/er.mmd`](docs/er.mmd)（GitHub / Mermaid 可直接渲染）。

---

## 3. 快速开始

```bash
# 1) PostgreSQL 16 测试库（库名必须含 test，测试会重建 public schema）
createdb -h 127.0.0.1 -p 5432 clawhunt_2056_test

# 2) 安装依赖
/opt/homebrew/bin/python3.12 -m venv .venv      # 或系统 python3.11+
.venv/bin/pip install -r requirements.txt

# 3) 建表
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/clawhunt_2056_test'
.venv/bin/alembic upgrade head

# 4) 全量测试
export TEST_DATABASE_URL="$DATABASE_URL"
EVIDENCE_OUT=evidence/test-results.txt ./scripts/test.sh

# 5) 迁移往返 + 漂移检查
DATABASE_URL="$DATABASE_URL" ./scripts/migration-check.sh | tee evidence/migration-check.txt
```

可选 Docker 测试库（端口 55437，独立于本机其他 PostgreSQL）：

```bash
docker compose -f docker-compose.test.yml up -d
export TEST_DATABASE_URL='postgresql+psycopg://clawhunt:clawhunt@127.0.0.1:55437/clawhunt_2056_test'
```

服务层调用示例（无 HTTP 层，由接口工单注入 Session）：

```python
from app.enums import Origin, Stage
from app.services import create_opportunity, record_meeting, record_outcome

opp = create_opportunity(
    session,
    org_id=org,
    site_id=site,
    party_a_company_id=demand_company,
    party_b_company_id=supply_company,
    origin=Origin.AI_MATCH,
    match_id=match_id,
    owner_staff_id=staff,
)
record_meeting(session, opp, meeting_type="one_on_one", meeting_at=meeting_time, participants=[...])
record_outcome(session, opp, outcome="deal", deal_cents=12500)
```

---

## 4. 目录

```
app/
  db.py                         # DATABASE_URL、engine/session（唯一连接串来源）
  enums.py                      # Origin/Stage/Outcome/MeetingType/LostReason + 中文标签 + 顺序
  models/
    base.py                     # 统一字段：UUID / org_id / site_id / 时间戳 / 软删除
    opportunity.py              # 主表 + 8 个 CHECK + 6 个索引
    opportunity_meeting.py      # 对接记录（类型 / 时间 / 参与方 / 纪要 / 活动）
    opportunity_stage_log.py    # 阶段留痕（from / to / 操作人 / 原因 / 时间）
  services/opportunities.py     # 创建入口、状态机、对接记录、结果、关闭
migrations/
  env.py                        # 只认 DATABASE_URL
  versions/0001_opportunity.py  # 三张表 + 约束 + 索引，可逆
tests/                          # 149 项，真实 PostgreSQL 16
scripts/test.sh                 # 测试入口（可输出 evidence）
scripts/migration-check.sh      # upgrade → downgrade → upgrade → alembic check
docs/er.mmd                     # Mermaid ER 图
evidence/                       # 环境、测试、迁移的真实输出
```

---

## 5. 数据模型

### 5.1 `opportunity`（撮合商机）

| 字段 | 类型 | 空 | 说明 |
|---|---|---|---|
| `id` | UUID PK | 否 | `gen_random_uuid()` |
| `org_id` / `site_id` | UUID | 否 | 租户 / 站点，统一字段 |
| `created_at` / `updated_at` / `deleted_at` | timestamptz | 否 / 否 / 是 | 统一字段，`deleted_at` 软删除 |
| `created_by` | UUID | 是 | 创建人 |
| `source_item_id` | UUID | 是 | 需求条目；**员工人工引荐时可空** |
| `match_id` | UUID | 是 | AI 匹配记录；`origin=ai_match` 时必填 |
| `connect_request_id` | UUID | 是 | 对接请求；`origin=member_initiated` 时必填 |
| `party_a_company_id` | UUID | 否 | 需求方企业 |
| `party_b_company_id` | UUID | 否 | 供给方企业，**必须与 party_a 不同** |
| `origin` | varchar(20) | 否 | `ai_match` / `member_initiated` / `staff_intro` / `event` |
| `event_id` | UUID | 是 | 活动；`origin=event` 时必填 |
| `owner_staff_id` | UUID | 否 | 负责会员经理 |
| `stage` | varchar(20) | 否 | `follow_up` / `meeting` / `outcome` / `closed`，默认 `follow_up` |
| `stage_entered_at` | timestamptz | 否 | 进入当前阶段的时间，默认 `now()` |
| `first_contacted_at` | timestamptz | 是 | 首次联系时间 |
| `party_a_confirmed_at` / `party_b_confirmed_at` | timestamptz | 是 | 双方确认时间 |
| `outcome` | varchar(15) | 是 | `deal` / `no_deal` / `on_hold` |
| `lost_reason` | varchar(30) | 是 | 未成交原因字典值（见 §10） |
| `deal_cents` | bigint | 是 | 成交金额，**单位分（整数），可为 0，不可为负** |
| `feedback_a` / `feedback_b` | smallint | 是 | 需求方 / 供给方反馈，**1–5** |
| `closed_at` | timestamptz | 是 | 关闭时间，进入 `closed` 时写入 |
| `contributors` | uuid[] | 否 | 贡献员工数组，默认 `{}` |

索引：`(org_id, site_id)`、`party_a_company_id`、`party_b_company_id`、`owner_staff_id`、
`stage`、`created_at`。

### 5.2 `opportunity_meeting`（线下对接）

| 字段 | 类型 | 空 | 说明 |
|---|---|---|---|
| `opportunity_id` | UUID FK | 否 | → `opportunity.id`，`ON DELETE CASCADE` |
| `meeting_type` | varchar(20) | 否 | `one_on_one`（一对一引荐）/ `salon`（沙龙）/ `closed_door`（闭门会） |
| `meeting_at` | timestamptz | 否 | 对接时间 |
| `participants` | jsonb | 否 | 参与方数组 `[{role, company_id, staff_id, name}]`，`role` ∈ `party_a/party_b/staff/guest` |
| `summary` | text | 是 | 纪要摘要 |
| `event_id` | UUID | 是 | 关联活动 |

索引：`(opportunity_id, meeting_at)`。

### 5.3 `opportunity_stage_log`（阶段留痕）

| 字段 | 类型 | 空 | 说明 |
|---|---|---|---|
| `opportunity_id` | UUID FK | 否 | → `opportunity.id`，`ON DELETE CASCADE` |
| `from_stage` | varchar(20) | 是 | 来源阶段；**创建时的首条为空**，表示“创建即进入 ③” |
| `to_stage` | varchar(20) | 否 | 目标阶段 |
| `operator_staff_id` | UUID | 是 | 操作人；系统自动推进时为空 |
| `reason` | text | 是 | 变更原因（回退时必填） |
| `occurred_at` | timestamptz | 否 | 业务发生时间，默认 `now()` |

索引：`(opportunity_id, occurred_at)`。日志只追加，不做更新与软删除。

---

## 6. 约束与校验矩阵

数据库约束是最后一道防线；服务层提前给出可读错误。两层使用同一份枚举（`app/enums.py`），
`tests/test_enums.py` 比对 DDL 的 `CHECK` 字面量与 Python 枚举，任何一侧改词表都会失败。

| 规则 | 数据库 | 服务层 | 测试 |
|---|---|---|---|
| `party_a ≠ party_b` | `ck_opportunity_party_distinct` | `create_opportunity` 抛 `OpportunityValidationError` | AC-2、`test_db_constraints`、`test_service` |
| `deal_cents ≥ 0` | `ck_opportunity_deal_cents_nonneg` | 负数 / 非整数直接拒绝 | AC-3、`test_db_constraints`、`test_service` |
| `stage` 只允许四值 | `ck_opportunity_stage` | `advance_stage` 枚举校验 | AC-4、`test_enums` |
| `outcome` 只允许三值（可空） | `ck_opportunity_outcome` | `record_outcome` 枚举校验 | AC-4、`test_enums` |
| `origin` 只允许四值 | `ck_opportunity_origin` | `create_opportunity` 枚举校验 | `test_db_constraints` |
| `lost_reason` 只允许字典值 | `ck_opportunity_lost_reason` | `record_outcome` 枚举校验 | `test_db_constraints` |
| `feedback` 1–5（可空） | `ck_opportunity_feedback_a/b_range` | 越界拒绝 | `test_db_constraints` |
| `contributors` 非空 | `NOT NULL` + 默认 `{}` | 创建时去重 | `test_db_constraints` |
| 对接类型三值 | `ck_opportunity_meeting_type` | `record_meeting` 校验 | `test_service` |
| 参与方必须是数组 | `ck_opportunity_meeting_participants_array` | 非空 + `role` 枚举 | `test_service` |
| 阶段日志 from/to 合法 | `ck_opportunity_stage_log_from/to` | 状态机校验 | `test_service` |

### 6.1 `origin` 与关联字段矩阵

| origin | 必填关联字段 | 可空关联字段 |
|---|---|---|
| `ai_match` | `match_id` | `source_item_id`、`connect_request_id`、`event_id` |
| `member_initiated` | `connect_request_id` | `source_item_id`、`match_id`、`event_id` |
| `staff_intro` | —（`source_item_id` 可为空） | 其余全部 |
| `event` | `event_id` | 其余全部 |

字段在数据库层保持可空（不同入口需要不同子集），由 `create_opportunity` 按入口强制。

### 6.2 状态机

- 创建即进入 `follow_up`，写首条日志（`from_stage = null`）。
- **前进**（`follow_up → meeting → outcome → closed`）无需原因；允许跳级（例如未线下对接直接成交）。
- **回退**必须填写 `reason`（静默回退会掩盖商机退步）；回退禁止离开 `closed`。
- 进入 `closed` 前必须先写 `outcome`；`closed` 是终态，不能再改阶段或结果。
- `outcome` 写入规则：`deal` 必须有 `deal_cents`；`no_deal` 必须有 `lost_reason` 且不得有金额；
  `on_hold` 不得有金额，且不能直接关闭（需先改为 `deal` 或 `no_deal`）。
- 每次阶段变化写一条 `opportunity_stage_log`，并更新 `stage_entered_at`；进入 `closed` 时写 `closed_at`。

> 说明：回退需原因、跳级允许、`on_hold` 不可直接关闭，是本单为可用性补充的领域规则，
> 落库字段不受影响；若客户业务口径不同，只改 `app/services/opportunities.py` 一处。

---

## 7. 迁移

- 单一 revision `0001_opportunity`，`downgrade` 逆序删除三张表及其索引，**不依赖** `DROP TYPE`
  （枚举用 `VARCHAR + CHECK` 表达），因此回滚干净、无残留类型。
- 表的创建顺序为 `opportunity → opportunity_meeting → opportunity_stage_log`；回滚反之。
- `migrations/env.py` 只接受 `DATABASE_URL`，不会静默连到开发者默认库。
- `scripts/migration-check.sh` 实测输出：`upgrade head → downgrade base → upgrade head → alembic check`
  全部成功，`No new upgrade operations detected`（见 `evidence/migration-check.txt`）。

---

## 8. 依赖与 Mock 说明

| 依赖 | 本单处理 | 对接点 |
|---|---|---|
| S2-CRM（企业、员工） | 只存 UUID，不建外键 | 接口层校验企业在册、员工在职后传 UUID；本单不查 CRM |
| 需求条目 / 匹配记录 / 对接请求 / 活动 | 只存 UUID，不建外键 | 各对象所属工单保证存在性；`source_item_id` 在 `staff_intro` 可空 |
| 身份与权限 | 不在本单范围 | 接口工单解析 principal 后传 `owner_staff_id` / `created_by` |
| 消息通知 / 定时任务 | 不在本单范围 | 消费 `stage` 与 `stage_entered_at` |

不建跨模块外键是刻意选择：1500 个工单由核心团队统一集成，若本单先建外键，会与 S2-CRM 的建表
顺序耦合，导致迁移在集成环境里失败。README 在此写明对接责任边界。

---

## 9. 测试与证据

| 文件 | 覆盖 |
|---|---|
| `tests/test_migration.py` | 临时库上 `upgrade → downgrade → upgrade`，版本号、表存在性、零漂移 |
| `tests/test_db_schema.py` | 列、类型、可空性、默认值、索引、外键 `CASCADE`、12 个 CHECK |
| `tests/test_db_constraints.py` | 绕过服务层直接写库，逐条验证非法值被数据库拒绝；合法边界（0 分、1/5 分反馈）通过 |
| `tests/test_service.py` | 四个创建入口、必填关联字段、状态机、回退原因、对接记录、结果规则、关闭规则、贡献人去重 |
| `tests/test_enums.py` | Python 枚举 ↔ DDL `CHECK` 双向一致、中文标签完整、阶段顺序 |
| `tests/test_acceptance.py` | 工单四条验收标准逐条对应 |

实测（`evidence/test-results.txt`）：

```
149 passed
```

迁移实测（`evidence/migration-check.txt`）：

```
0001_opportunity (head)          # upgrade
(empty)                          # downgrade base
0001_opportunity (head)          # upgrade again
No new upgrade operations detected.
```

---

## 10. 字典（`lost_reason`）

| 值 | 中文 |
|---|---|
| `demand_withdrawn` | 需求方撤回需求 |
| `budget_mismatch` | 预算不匹配 |
| `region_mismatch` | 服务地域不匹配 |
| `timing_conflict` | 时间冲突 |
| `no_intent` | 双方无成交意愿 |
| `qualification_mismatch` | 资质或能力不匹配 |
| `other` | 其他 |

字典常量在 `app/enums.py: LostReason` 与 `LOST_REASON_LABELS`，与数据库 CHECK 同步；
S1-DD 字典工单冻结词表后只需改这一处并补一条迁移。

---

## 11. 验收映射

| 工单验收标准 | 实现 | 证据 |
|---|---|---|
| ① 迁移 upgrade / downgrade 均成功 | `migrations/versions/0001_opportunity.py` 可逆 | `test_migration.py`、`test_ac1_*`、`evidence/migration-check.txt` |
| ② party_a 与 party_b 相同时保存失败 | `ck_opportunity_party_distinct` + 服务层校验 | `test_ac2_*`、`test_db_constraints.py::test_party_a_and_party_b_must_differ` |
| ③ deal_cents 为负数时保存失败 | `ck_opportunity_deal_cents_nonneg` + 服务层校验 | `test_ac3_*`、`test_service.py::test_deal_rejects_negative_amount` |
| ④ stage 与 outcome 写入非法值被拒绝 | `ck_opportunity_stage` / `ck_opportunity_outcome` + 枚举校验 | `test_ac4_*`（4 组非法值）、`test_enums.py` |

---

## 12. 数据与保密

- 测试只用虚构 UUID 与虚构纪要文本，仓库内不出现客户名称、真实企业、真实联系人。
- 企业/员工等外部对象只以 UUID 引用，测试不查询任何外部系统。
- 配置、连接串、密钥只从环境变量读取；仓库内无凭据。
- 不引入任何向境外发送数据的第三方 SDK；本仓库除 PostgreSQL 外无出站请求。
