# Playbook

## 1. 接收交接

业务 Skill 必须提供：

- accepted 文件
- `assetKind`
- `externalTool`
- `externalRunId`
- 项目根目录中的 `bindingFile`
- 首次调用时的稳定项目名或明确项目 ID

本 Skill 不重新做业务 QA，只验证 accepted 状态、文件身份和平台合同。

## 2. 首次项目绑定

1. 验证受管凭据。
2. 读取 `/projects`。
3. 有项目 ID：按 UUID 精确匹配。
4. 只有项目名：按完整名称精确匹配。
5. 零个匹配：创建一次。
6. 一个匹配：复用。
7. 多个匹配：停止，不能猜。
8. 将项目 ID、名称、URL、API 根和空资产台账写入
   `baiende-project.json`。

## 3. 后续项目复用

1. 读取同一 binding。
2. 通过 `/projects` 回读并精确确认项目仍可访问。
3. 检查命令参数不得与 binding 冲突。
4. 禁止扫描目录或按时间推断另一个项目。

## 4. 项目媒体上传

1. 计算文件 SHA-256、字节数和 MIME。
2. 检查 `assetKind` 与文件类型。
3. 检查 binding 台账：
   - 同稳定路径同哈希：幂等跳过；
   - 同路径不同哈希：失败并要求改版本名。
4. 图片/视频执行单次原子 `POST /projects/{id}/assets`。
5. standalone HTML 执行 `POST /projects/{id}/preview3d`。
6. 回读 `/projects/{id}/assets`，取得平台资产 ID。
7. 更新 binding 台账并写发布回执。

## 5. 社区预览

1. 读取 `baiende.community-publication-spec.v1`。
2. 校验项目 binding、来源 Skill、HTML snapshot 和图片 HTTPS 映射。
3. 检查 spec 不包含平台布局实现字段。
4. 先用 `--dry-run` 做纯本地合同检查。
5. 不带 `--dry-run/--execute` 时调用 `/community/html-snapshots/preview`。
6. 保存诊断和 `communityPostPayload`，状态为 `preview_only`。
7. 展示给 Agent/用户核对；不公开。

## 6. 社区公开

只有用户本轮明确确认时：

```bash
node scripts/publish_community_post.mjs \
  community-publication-spec.json \
  --binding-file <project>/baiende-project.json \
  --out community-publication-receipt.json \
  --execute \
  --confirm-public
```

脚本必须先重新生成预览，再使用平台返回的 `communityPostPayload` 发布。保存社区
post ID、share path 和 share URL。

## 7. 个人资产库

- `list_library_items.mjs`：只读查找平台风格、灯光、材质和家具。
- `upload_library_item.mjs`：将用户有权使用的素材写入个人资产库。
- 个人资产默认不公开；公开仍走社区流程。

## 8. 失败处理

- `401/403`：检查受管凭据和权限，停止，不切换匿名上传。
- `410/404`：确认 API 根固定为 `/api/v1`，不使用旧路径。
- 项目多重匹配：要求明确项目 ID。
- 同名不同内容：显式改版本名。
- HTML 加载失败：退回上游制作真正 standalone，不能临时引入外链 runtime。
- 社区预览诊断失败：退回上游修 snapshot，不绕过预览直接发布。
- 网络或平台错误：保存请求摘要和错误，不重试写操作，等待明确后续动作。
