# 数据合同

## 输入模型

`rooms`、`walls`、`openings`、`furniture` 必须为可读数组。开口用 `wallId` 绑定宿主墙；家具用 `roomId` 绑定空间。

## 输出 `interior.circulation-result.v3`

```json
{
  "schema": "interior.circulation-result.v3",
  "schemaVersion": "3.1-advisory",
  "policy": {
    "blocking": false,
    "userLayoutPreserved": true,
    "cameraContinuesRegardless": true
  },
  "risks": [],
  "verdict": {
    "accepted": true,
    "cameraWorkflowAllowed": true
  }
}
```

`risks` 可包含不可达空间、门口接近家具和疑似过窄等提示。它们只描述当前事实，不拥有修改权或阻断权。
