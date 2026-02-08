# 跨账号 Bedrock 访问配置指南

本指南介绍如何配置代理服务以跨账号访问 AWS Bedrock。

## 📋 使用场景

当你的代理服务部署在**账号 A**，但需要访问**账号 B** 的 Bedrock 资源时，可以使用此功能。

典型场景：
- 代理服务在开发账号，Bedrock 在生产账号
- 多租户架构，不同客户使用不同账号的 Bedrock
- 组织内跨部门资源共享

---

## 🏗️ 架构说明

```
┌─────────────────────────────────────────────────────────────┐
│ 账号 A (代理服务所在账号)                                      │
│                                                             │
│  ┌──────────────────────────────────────────┐               │
│  │ Anthropic API Proxy                       │               │
│  │                                           │               │
│  │  1. 使用账号 A 的凭证                      │               │
│  │  2. 调用 STS AssumeRole                   │ ─────────┐    │
│  │     Role: BedrockAccessRole (账号 B)      │          │    │
│  │  3. 获取临时凭证（有效期 1 小时）           │          │    │
│  │  4. 使用临时凭证访问 Bedrock              │          │    │
│  └──────────────────────────────────────────┘          │    │
└─────────────────────────────────────────────────────────│────┘
                                                          │
                                                          │ STS AssumeRole
                                                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 账号 B (Bedrock 所在账号)                                     │
│                                                             │
│  ┌──────────────────┐        ┌──────────────────────┐       │
│  │ IAM Role         │◄───────│ AWS Bedrock          │       │
│  │ BedrockAccessRole│        │ (Claude, Qwen, etc.) │       │
│  │                  │        └──────────────────────┘       │
│  │ Trust: 账号 A    │                                       │
│  │ Permissions:     │                                       │
│  │ - bedrock:*      │                                       │
│  └──────────────────┘                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 配置步骤

### 步骤 1: 在目标账号 (账号 B) 创建 IAM Role

#### 1.1 创建 Role

登录 AWS Console (账号 B) → IAM → Roles → Create role

**Trust relationships (信任关系)**：
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111111111111:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {}
    }
  ]
}
```

> ⚠️ 将 `111111111111` 替换为你的**账号 A** 的 AWS 账号 ID

#### 1.2 添加权限策略

创建一个内联策略或附加以下策略：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:ListFoundationModels",
        "bedrock:GetFoundationModel"
      ],
      "Resource": "*"
    }
  ]
}
```

**可选：限制访问特定模型**：
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
        "arn:aws:bedrock:us-west-2::foundation-model/qwen.qwen3-coder-480b-a35b-v1:0"
      ]
    }
  ]
}
```

#### 1.3 记录 Role ARN

创建完成后，记录 Role 的 ARN，格式类似：
```
arn:aws:iam::222222222222:role/BedrockAccessRole
```

---

### 步骤 2: 在源账号 (账号 A) 配置权限

确保代理服务的 IAM 角色（或 IAM 用户）有权限 AssumeRole：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::222222222222:role/BedrockAccessRole"
    }
  ]
}
```

> ⚠️ 将 `222222222222` 和 `BedrockAccessRole` 替换为步骤 1 创建的 Role ARN

---

### 步骤 3: 配置代理服务环境变量

根据你的部署方式选择对应的配置方法：

#### 方式 A: 本地开发 (.env 文件)

在项目根目录创建或编辑 `.env` 文件：

```bash
# 当前账号 A 的基本配置
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-access-key-id>
AWS_SECRET_ACCESS_KEY=<your-secret-access-key>

# 跨账号 Bedrock 配置
BEDROCK_CROSS_ACCOUNT_ROLE_ARN=arn:aws:iam::222222222222:role/BedrockAccessRole
BEDROCK_REGION=us-west-2

# DynamoDB 配置（仍在账号 A）
DYNAMODB_API_KEYS_TABLE=anthropic-proxy-api-keys
DYNAMODB_USAGE_TABLE=anthropic-proxy-usage

# 其他配置...
MASTER_API_KEY=sk-your-master-key
```

#### 方式 B: Docker Compose 部署

编辑 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  api-proxy:
    image: anthropic-bedrock-proxy:latest
    ports:
      - "8000:8000"
    environment:
      # 基本配置
      - AWS_REGION=us-east-1
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

      # 跨账号配置
      - BEDROCK_CROSS_ACCOUNT_ROLE_ARN=arn:aws:iam::222222222222:role/BedrockAccessRole
      - BEDROCK_REGION=us-west-2

      # DynamoDB
      - DYNAMODB_ENDPOINT_URL=http://dynamodb-local:8000

      # 其他配置
      - MASTER_API_KEY=sk-your-master-key
```

#### 方式 C: AWS ECS 部署

**选项 1 - CDK 配置**：

编辑 `cdk/lib/ecs-stack.ts`，在容器定义的 environment 部分添加：

```typescript
environment: {
  AWS_REGION: props.config.region,
  // ... 其他环境变量

  // 跨账号配置
  BEDROCK_CROSS_ACCOUNT_ROLE_ARN: "arn:aws:iam::222222222222:role/BedrockAccessRole",
  BEDROCK_REGION: "us-west-2",
}
```

**选项 2 - ECS Console 配置**：

1. 进入 ECS → Task Definitions
2. 创建新的 revision
3. 在 Container definitions → Environment variables 添加：
   - `BEDROCK_CROSS_ACCOUNT_ROLE_ARN` = `arn:aws:iam::222222222222:role/BedrockAccessRole`
   - `BEDROCK_REGION` = `us-west-2`

**选项 3 - 使用 ECS Task Role（推荐）**：

为 ECS Task 附加一个 IAM Role，包含 AssumeRole 权限：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::222222222222:role/BedrockAccessRole"
    }
  ]
}
```

然后在环境变量中只需配置：
- `BEDROCK_CROSS_ACCOUNT_ROLE_ARN`
- `BEDROCK_REGION`

不需要配置 `AWS_ACCESS_KEY_ID` 和 `AWS_SECRET_ACCESS_KEY`（ECS 会自动使用 Task Role）。

---

### 步骤 4: 启动服务并验证

#### 启动服务

```bash
# 本地开发
uv run uvicorn app.main:app --reload

# Docker Compose
docker-compose up -d

# AWS ECS
# 通过 CDK 或 Console 部署
```

#### 验证配置

**1. 检查日志**：

```bash
# Docker
docker-compose logs -f api-proxy

# 本地
# 查看终端输出
```

你应该看到类似的日志：
```
[INFO] Initializing Bedrock service with cross-account role
[INFO] Assuming role: arn:aws:iam::222222222222:role/BedrockAccessRole
[INFO] Successfully obtained temporary credentials
```

**2. 测试 API 调用**：

```bash
curl http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-your-api-key" \
  -d '{
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 100,
    "messages": [
      {"role": "user", "content": "Hello from cross-account!"}
    ]
  }'
```

**3. 检查 CloudTrail（可选）**：

在账号 B 的 CloudTrail 中，你应该能看到：
- `AssumeRole` 事件（来自账号 A）
- `bedrock:InvokeModel` 事件（使用 assumed role）

---

## 📊 配置参数说明

| 环境变量 | 必填 | 默认值 | 说明 |
|---------|------|--------|------|
| `BEDROCK_CROSS_ACCOUNT_ROLE_ARN` | 否 | `None` | 目标账号的 IAM Role ARN，格式：`arn:aws:iam::账号ID:role/角色名`。如果不配置，使用本地账号凭证 |
| `BEDROCK_REGION` | 否 | `us-east-1` | Bedrock 服务所在的区域 |
| `AWS_REGION` | 是 | - | 当前账号的区域（用于 STS 和 DynamoDB） |
| `AWS_ACCESS_KEY_ID` | 条件 | - | 当前账号的访问密钥（ECS 使用 Task Role 时不需要） |
| `AWS_SECRET_ACCESS_KEY` | 条件 | - | 当前账号的密钥（ECS 使用 Task Role 时不需要） |

---

## 🔒 安全最佳实践

### 1. 最小权限原则

**限制 Bedrock 访问的模型**：
```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream"
  ],
  "Resource": [
    "arn:aws:bedrock:us-west-2::foundation-model/anthropic.*"
  ]
}
```

**限制 AssumeRole 的来源**：
```json
{
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::111111111111:role/specific-ecs-task-role"
  },
  "Action": "sts:AssumeRole"
}
```

### 2. 添加条件约束

**限制会话持续时间**：
```json
{
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::111111111111:root"
  },
  "Action": "sts:AssumeRole",
  "Condition": {
    "NumericLessThan": {
      "sts:DurationSeconds": 3600
    }
  }
}
```

**限制来源 IP**（可选）：
```json
{
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::111111111111:root"
  },
  "Action": "sts:AssumeRole",
  "Condition": {
    "IpAddress": {
      "aws:SourceIp": [
        "1.2.3.4/32",
        "5.6.7.0/24"
      ]
    }
  }
}
```

### 3. 启用 CloudTrail 监控

在账号 B 启用 CloudTrail，监控跨账号访问：
- 追踪所有 `AssumeRole` 事件
- 追踪 Bedrock API 调用
- 设置异常访问告警

---

## ❓ 常见问题

### Q1: 我只有一个 AWS 账号，需要配置跨账号吗？

**A:** 不需要。如果不配置 `BEDROCK_CROSS_ACCOUNT_ROLE_ARN`，代理会自动使用本地账号凭证（原有行为）。

### Q2: 临时凭证多久刷新一次？

**A:** 临时凭证有效期是 **1 小时**（3600 秒）。代理服务在每次初始化 BedrockService 时都会重新 AssumeRole，获取新的临时凭证。

### Q3: 可以同时访问多个账号的 Bedrock 吗？

**A:** 当前版本只支持配置一个跨账号 Role。如果需要访问多个账号，有以下方案：
- 部署多个代理实例，每个配置不同的 Role
- 修改代码支持多账号路由（需要自定义开发）

### Q4: AssumeRole 失败，提示 "Access Denied"

**可能原因**：
1. **信任关系未正确配置**：检查账号 B 的 Role Trust Policy 是否包含账号 A
2. **账号 A 缺少 AssumeRole 权限**：确认代理服务的 IAM 角色有 `sts:AssumeRole` 权限
3. **Region 不匹配**：确认 Bedrock 模型在目标 Region 可用
4. **Role ARN 格式错误**：检查 ARN 格式是否正确

### Q5: 如何查看 AssumeRole 是否成功？

**方法 1 - 查看应用日志**：
```bash
docker-compose logs api-proxy | grep -i "assume"
```

**方法 2 - 检查 CloudTrail**：
在账号 B 的 CloudTrail 中搜索：
- Event name: `AssumeRole`
- User identity: 来自账号 A

**方法 3 - 测试 API 调用**：
成功的调用会使用账号 B 的 Bedrock 配额和计费。

### Q6: DynamoDB 和 Bedrock 在不同账号怎么办？

代理服务支持 DynamoDB 和 Bedrock 在不同账号：
- DynamoDB 使用本地账号凭证（`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`）
- Bedrock 使用跨账号 Role（`BEDROCK_CROSS_ACCOUNT_ROLE_ARN`）

### Q7: 跨账号会影响性能吗？

**影响很小**：
- AssumeRole 调用只在服务初始化时执行（约 100-200ms）
- 临时凭证缓存 1 小时，期间不需要重新 AssumeRole
- Bedrock API 调用本身的延迟不受影响

---

## 🧪 测试检查清单

部署完成后，按照以下清单验证配置：

- [ ] 在账号 B 创建了 IAM Role
- [ ] Role 的 Trust Policy 包含账号 A
- [ ] Role 有 Bedrock 访问权限
- [ ] 账号 A 有 AssumeRole 权限
- [ ] 配置了 `BEDROCK_CROSS_ACCOUNT_ROLE_ARN` 环境变量
- [ ] 配置了 `BEDROCK_REGION` 环境变量
- [ ] 服务启动日志显示 AssumeRole 成功
- [ ] API 调用能正常返回结果
- [ ] CloudTrail 显示跨账号访问记录

---

## 📚 相关文档

- [AWS STS AssumeRole 官方文档](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)
- [IAM Roles 跨账号访问指南](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_common-scenarios_aws-accounts.html)
- [Bedrock IAM 权限参考](https://docs.aws.amazon.com/bedrock/latest/userguide/security-iam.html)
- [项目主 README](./README.md)

---

## 💡 示例场景

### 场景 1: 开发/生产账号分离

```
开发账号 (111111111111)           生产账号 (222222222222)
    │                                   │
    ├─ 代理服务 (ECS)                   ├─ Bedrock (Claude, Qwen)
    ├─ DynamoDB (API Keys)              └─ IAM Role (BedrockAccessRole)
    └─ 环境变量:
        BEDROCK_CROSS_ACCOUNT_ROLE_ARN=arn:aws:iam::222222222222:role/BedrockAccessRole
```

### 场景 2: 多租户架构

```
管理账号 (主代理服务)
    │
    ├─ 租户 A: Role ARN → 账号 A 的 Bedrock
    ├─ 租户 B: Role ARN → 账号 B 的 Bedrock
    └─ 租户 C: Role ARN → 账号 C 的 Bedrock
```

> 注：多租户需要修改代码支持动态 Role 选择

---

## 🔄 版本历史

- **v1.0** (2025-02-09): 初始版本，支持单个跨账号 Role

---

如有问题，请在 GitHub Issues 中反馈。
