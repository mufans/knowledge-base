# Blind review calibration

`blind-review-sample.json` 是 16 页分层样本。评审者先独立填写六项 1–5 分、
逐项证据和 publish/update/reject 决策，不查看历史页面自评分，也不打开
`blind-review-key.json`。

完成盲审后再使用 key 对照页面类型、引用数量和反方证据，校准自动门禁。空白
`reviewer_scores` 和 `decision` 表示仍需真实人工判断，不能被仪表盘误报为已完成。
