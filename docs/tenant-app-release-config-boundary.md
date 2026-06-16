# 租户 App 发布配置边界

本文档用于开源 GitHub 模板说明：租户后台能改变 App 运行时展示，但不能改变已经封装进 iOS/Android 包或商店后台绑定的身份。

## 租户后台配置即可在 App 端生效

这些字段由租户后台保存到 Tenant Edge 公开配置，Flutter 只读取 `GET /config`、`GET /payment/options` 或相关公开接口。

| 材料 | App 端效果 | 是否需要重新封包 |
| --- | --- | --- |
| App 内品牌名 | App 内标题、会员中心、充值页、客服入口显示 | 否 |
| 模板风格 | `coolshow`、红果/抖音/河马/ReelShort 等布局和主题 | 否 |
| 支持语言、地区、币种展示 | 文案、地区可见性、支付包展示 | 否 |
| 隐私政策、服务条款、客服、账号删除 URL | 我的页、账号删除、支付说明、审核链接 | 否 |
| 登录方式可见性 | email/google/facebook/apple 登录按钮显隐 | 否 |
| 支付方式可见性 | IAP/Play Billing/Stripe/PayPal/银行卡/钱包/crypto/点卡入口显隐 | 否 |
| 分类展示名和隐藏分类 | 分类/剧场入口、筛选 chip、剧集卡片分类标签 | 否 |
| 点卡面额、批次、有效期、核销规则 | 会员中心点卡兑换入口和核销结果 | 否 |

注意：外部支付会继续受 `storeComplianceMode` 过滤。App Store 版默认只展示 IAP；Google Play 版默认只展示 Play Billing 或已批准地区能力；Android direct 才开放租户自有支付。

运行时保存链路：

```text
Tenant Portal POST /app-config
  -> Tenant Edge 使用租户 HMAC 签名
  -> API Worker POST /v1/tenant/app-config
  -> D1 tenant_app_configs
  -> Tenant Edge GET /config 合并公开配置
  -> Flutter 下一次拉取 /config 后渲染
```

`POST /app-config` 和 `/v1/tenant/app-config` 只接受公开运行时字段。顶层提交 Bundle ID、package name、Team ID、证书、Profile、keystore、OAuth/payment secret、webhook secret、银行凭证、钱包私钥、Cloudflare token 或 Stream signing key 会被拒绝。`releaseManifest` 只用于记录公开发布 handoff 元数据，例如 flavor、applicationId、bundleId、deepLinkScheme；它不会改变已经封装的二进制包。

## 租户后台配置入口 + 服务端/第三方后台完成后生效

这些能力不需要 Flutter 重新打包，但仅在服务端和第三方后台也完成后才真正可用。租户后台只保存公开状态、公开链接、商品 ID、启用状态和审核字段。

| 材料 | 还需要在哪里完成 | App 端效果 |
| --- | --- | --- |
| Google/Facebook/Apple OAuth client/app | provider 控制台 + Tenant Edge/API Worker 环境 | App 打开 Tenant Edge 返回的授权 URL |
| OAuth redirect/deep link 登记 | provider 控制台，使用已封包 scheme/domain | App 接收授权回调 |
| Stripe/PayPal 商户配置 | Stripe/PayPal 控制台 + Tenant Edge webhook/order config | App 创建订单并打开 checkout URL |
| 本地钱包/银行卡收款字段 | 租户服务端配置、审核规则、结算主体资料 | App 提交线下充值审核 |
| USDT/USDC 收款策略 | 服务端风控、公开收款说明、链和币种策略 | Android direct 或合规地区显示 crypto 入口 |
| IAP/Play Billing 商品映射 | Apple/Google 商品已创建，Tenant Edge 保存 product id 映射 | App 使用 store billing 并调用服务端验单 |

禁止把 OAuth 凭证值、支付 provider 凭证值、webhook 校验值、银行登录资料、钱包私钥、Cloudflare token 或 Worker 凭证写入 Flutter、GitHub、租户后台浏览器存储或公开 release 包。

## 必须封包或商店后台处理

这些配置不能通过租户后台刷新后直接改变已安装 App。

| 材料 | 原因 | 需要做什么 |
| --- | --- | --- |
| Apple Developer Team ID | 属于 Apple 账号/签名/商店记录，不是 App 运行时配置 | 租户在 Apple Developer/App Store Connect 配置，后台只记录公开状态 |
| Bundle ID | 写入 iOS target 和 App Store 记录 | 生成对应 iOS scheme/xcconfig 后重新打包上传 |
| iOS signing certificates / Profiles | 只在签名阶段使用 | 租户账号或受保护 CI 持有，不能进仓库 |
| App Store Connect app | 商店后台记录和审核状态 | 租户自行创建，后台只记录 app id/status/build |
| iOS IAP 商品创建 | Apple 后台商品必须存在并通过审核 | 在 App Store Connect 创建商品，Tenant Edge 只保存 product id 映射 |
| Sign in with Apple capability | 需要 Apple App ID capability 和 entitlements | Apple 后台启用并随 iOS 包封装 |
| Google Play 开发者账号 | 商店账号状态，不是 App 配置 | 租户自行申请和维护 |
| Android package name | 写入 Android applicationId 和 Play 记录 | 生成对应 flavor 后重新打包 |
| App signing/upload key | Android 签名材料 | 租户账号或受保护 CI 持有，不能进仓库 |
| Play Billing 商品创建 | Google Play 商品必须存在并可售 | 在 Play Console 创建商品，Tenant Edge 保存 product id 映射 |
| Data Safety / 隐私问卷 | Google Play 审核材料 | 租户在 Play Console 填写，后台只记录公开状态 |
| OAuth SHA-1/SHA-256 | 依赖最终签名证书 | 签名后在 provider 控制台登记 |
| App Links / Associated Domains | 原生 manifest/entitlements 和域名文件绑定 | 包内声明并在域名发布 assetlinks/apple-app-site-association |
| Launcher icon / 原生启动屏 | 系统桌面图标和 OS 启动屏来自原生包 | 重新生成 icon/splash 并重新封包 |
| 商店截图/商店名称/上架文案 | 商店后台元数据 | 租户在 Apple/Google 后台上传 |

## 开源模板默认边界

- Flutter 客户端不保存租户密钥、支付密钥、OAuth 密钥、Cloudflare token、Stream signing key、银行凭证或钱包私钥。
- App 只通过 Tenant Edge 获取公开配置、支付选项、登录授权 URL、钱包和播放授权结果。
- 租户官方点数钱包和 C 端用户钱包必须分账本；余额真值在 D1/Durable Objects，不在 KV 或 Flutter 本地。
- GitHub 示例只包含 demo 配置和示例素材，不包含真实商户、签名、OAuth、支付、银行或 crypto 凭证。
