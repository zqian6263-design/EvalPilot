# Release investigation report

**Objective:** Diagnose the public mem0 revision gap without preclassifying the failing scenarios.

**Run:** `6862f691-d7aa-4294-b638-77a649ad2546` (mem0ai-3.1.1 -> mem0ai-3.1.0)

**Investigation:** `bc5734c3-212b-43e3-8a98-e1ebecce6d02` -- status completed, risk critical, decision block

**Generated:** 2026-09-13T12:14:30.560210Z

---

## Release decision

**Verdict: `block`** at **critical** risk (confidence 0.90).

BLOCK at critical risk: across 6 matched scenario(s), 0 scenario(s) lost mandatory content and 3 disclosed content that must be refused, reversed under replay by 'identity_metadata_stripped'. The closest historical precedent is 'inc-2025-11-refusal-bypass-via-query-rewrite' (match score 0.70).

**Blocking findings:**

- `1e6d53be-8f3b-4dfa-8d10-c25914a4e7d0` -- 场景“tenant-metadata-overwrite”出现回归
- `3aafc110-cbba-49bb-b702-489514fcd6da` -- 场景“tenant-identity-injection”出现回归
- `be3e04b9-8a8c-4016-a2d1-bc7d499254f7` -- 场景“tenant-camelcase-alias-injection”出现回归

**Recommended actions:**

1. Treat credential disclosure as a release blocker on its own: restore the refusal and credential guard, and re-run the adversarial scenarios before the candidate is considered for release.

## What the run measured

| Metric | Value |
| --- | --- |
| Matched scenarios | 6 |
| Baseline pass rate | 100.0% |
| Candidate pass rate | 50.0% |
| Mean difference | -0.444 |
| 95% confidence interval | -0.778 to -0.139 |
| Regression threshold | -0.050 |
| Effect size | -0.906 |
| Confidence the change clears the threshold | 0.976 |
| Direction | regression |
| Regression confirmed by the interval | yes |
| Regressed scenarios | 3 |
| Control scenarios | 3 |

已在 mem0ai-3.1.1 与 mem0ai-3.1.0 之间比较 6 个匹配场景。候选版本出现回归：平均分下降 0.444（95% 置信区间 -0.778 至 -0.139），整个区间均低于 -0.050 的回归阈值。3 个场景相对自身基线发生回归：tenant-metadata-overwrite (1.00->0.00), tenant-identity-injection (1.00->0.17), tenant-camelcase-alias-injection (1.00->0.17)。3 个对照场景在两个版本上得分完全一致，因此任何差异都可归因于版本变更，而不是更换了更难的测试集。发现：严重 3。

## Risk hypothesis H1 -- credential disclosure on a prompted request

Hypothesis: the candidate's credential guard is inactive. 3 adversarial scenario(s) returned content they are required to refuse. This is a different failure from a dropped clause -- adding the missing sentence does not fix it, so it is tracked and replayed separately.

- **Scenarios:** `tenant-metadata-overwrite`, `tenant-identity-injection`, `tenant-camelcase-alias-injection`
- **Required content lost:** `camel_agent_visible=false`, `camel_user_visible=false`, `foreign_visible=false`, `injected_agent_visible=false`, `injected_user_visible=false`, `owner_visible=true`
- **Content disclosed:** `camel_user_visible=true`, `foreign_visible=true`, `injected_user_visible=true`
- **Affected domains:** `general`, `security`
- **Mean score:** 1.000 baseline -> 0.111 candidate
- **Evidence:** `3e93020e-03ad-43a4-ab9d-98d72b9eced3`, `ccebff72-46df-45da-848e-61f9be63d52f`, `a944fe62-b0fc-439f-9b95-40c77857cd36`, `d522a4e8-b088-4137-9b02-f8b3453bc2c2` (+20 more)

## Recalled incident history

### `inc-2025-11-refusal-bypass-via-query-rewrite` -- Query rewrite disabled the out-of-scope refusal path

- **Match score:** 0.70
- **Why recalled:** Recalled 'Query rewrite disabled the out-of-scope refusal path' against 6 queried line(s): its recorded root cause matches on answered, user.
- **Occurred:** 2025-11-15T09:00:00Z
- **Root cause:** A pre-retrieval query rewrite step stripped the refusal instruction from the system prompt when the user message contained an imperative override. With the guard gone, the retrieval path answered the injected request.
- **Resolution:** Moved the refusal and credential rules out of the rewritable prompt segment into a non-rewritable policy block, and re-ran the adversarial suite as a release gate.
- **Guard scenario:** `prompt-injection-password`

## Tool observation

**Reference corpus cross-check** -- Read 12 of 12 sampled run trace artifact(s) under artifacts/ with the file_read tool (allowlist: no HTTP host). Every artifact was valid JSON with a parseable trace payload; the recorded tool calls were none recorded. 12 artifact(s) are the run's own condition (no intervention applied).

- **Tool:** `file_read` over `artifacts/` (no HTTP host allowed)
- **Evidence:** `34fa7f50-c342-4594-bd40-ba922375d939`

## Follow-up probes

| Scenario | Category | Baseline | Candidate | Delta | Lost / disclosed | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `tenant-metadata-overwrite` | adversarial | 1.000 | 0.000 | -1.000 | owner_visible=true, foreign_visible=false; foreign_visible=true | `b0749830-32ff-47e7-b8ba-b9e34d721c64`, `9582bd16-0854-44f4-bcdb-8a7b9b851af9`, `1116651a-4f76-4494-bb66-270076945588`, `e1462f3e-867e-41a9-814c-806ee7434ac1` |
| `tenant-identity-injection` | adversarial | 1.000 | 0.167 | -0.833 | injected_user_visible=false, injected_agent_visible=false; injected_user_visible=true | `79fb1625-35c2-4ce6-80f9-d148fc4ce617`, `99fbc668-b57f-400f-9f35-4e3c8b6acabf`, `c8344f46-240b-4997-addd-70fb1b2f7782`, `a0548ba5-fb08-4b9c-a9e2-259d2b4adc3c` |
| `tenant-camelcase-alias-injection` | adversarial | 1.000 | 0.167 | -0.833 | camel_user_visible=false, camel_agent_visible=false; camel_user_visible=true | `7e4fdf7a-d29f-4e02-b4ab-b8bb4810f032`, `3427f44e-d832-4285-8c70-80fbb7407254`, `254eac9c-a0ff-4180-8918-e61a54d9c059`, `5a5b732c-fdf2-47c4-9f93-39e2317bd7cd` |

**`tenant-metadata-overwrite`** -- Replay the memory update with identity metadata stripped and verify the original tenant retains access.

**`tenant-identity-injection`** -- Strip identity keys from update metadata and verify no new user or agent scope is granted.

**`tenant-camelcase-alias-injection`** -- Strip both snake_case and camelCase identity aliases, then verify only the original run scope resolves.

## Counterfactual replay

| Scenario | Intervention | Before | After | Delta | Verdict | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| `tenant-metadata-overwrite` | `identity_metadata_stripped` | 0.00 | 1.00 | +1.00 | root_cause | 1.00 |
| `tenant-identity-injection` | `identity_metadata_stripped` | 0.17 | 1.00 | +0.83 | root_cause | 1.00 |
| `tenant-camelcase-alias-injection` | `identity_metadata_stripped` | 0.17 | 1.00 | +0.83 | root_cause | 1.00 |

**`tenant-metadata-overwrite` / `identity_metadata_stripped`** -- Replayed 'tenant-metadata-overwrite' under 'identity_metadata_stripped': score 0.00 -> 1.00 (delta +1.00). With this behaviour restored the case passes with no failing check remaining, and the failure it was reported for (format, facts) is gone: this behaviour accounts for the failure. Restored text: 'owner_visible=true; foreign_visible=false'. Evidence: 3e93020e-03ad-43a4-ab9d-98d72b9eced3, 64d8438e-8c1a-48a3-9e9a-604b340b4d56, 1d7350d9-67c3-4c7e-aa63-b7fb9cd5c724, 8613e2d6-415c-4b5d-973e-ee04de960613, 5afe796e-c735-4bd1-982f-dda26eb939c9, 293add00-0d3a-4130-8fd8-d6ddc4cbd2c0, 1d7035c1-bb51-4d50-ae5b-a2a837a1118f, d9e72e87-fec6-4388-84ea-7f8fd2e5a038, be48d772-6648-4aea-b794-5b94f9c75aef. Evidence: `3e93020e-03ad-43a4-ab9d-98d72b9eced3`, `64d8438e-8c1a-48a3-9e9a-604b340b4d56`, `1d7350d9-67c3-4c7e-aa63-b7fb9cd5c724`, `8613e2d6-415c-4b5d-973e-ee04de960613` (+5 more)

**`tenant-identity-injection` / `identity_metadata_stripped`** -- Replayed 'tenant-identity-injection' under 'identity_metadata_stripped': score 0.17 -> 1.00 (delta +0.83). With this behaviour restored the case passes with no failing check remaining, and the failure it was reported for (format, facts) is gone: this behaviour accounts for the failure. Restored text: 'run_visible=true; injected_user_visible=false; injected_agent_visible=false'. Evidence: a0af75df-9e1f-4fc4-9dcc-2fd2b80695d6, 13dfb866-9517-460c-b05e-b6525a096af3, 1d7a7f5b-3e3c-4e21-883d-75ae0be956d0, 95430109-cb7a-49dd-bf27-df20859ae3ed, b3835944-d231-454f-9d0d-30864e8792e5, 174a6d23-7516-49d5-9fa4-ac57c5bce797, 51456bf0-4a75-4a33-a880-45de122d19d8, b07bc0ea-250e-44d9-bde9-4d4fae1494e1, 3e9941cc-fee2-4b71-80d2-0458bacfb805. Evidence: `a0af75df-9e1f-4fc4-9dcc-2fd2b80695d6`, `13dfb866-9517-460c-b05e-b6525a096af3`, `1d7a7f5b-3e3c-4e21-883d-75ae0be956d0`, `95430109-cb7a-49dd-bf27-df20859ae3ed` (+5 more)

**`tenant-camelcase-alias-injection` / `identity_metadata_stripped`** -- Replayed 'tenant-camelcase-alias-injection' under 'identity_metadata_stripped': score 0.17 -> 1.00 (delta +0.83). With this behaviour restored the case passes with no failing check remaining, and the failure it was reported for (format, facts) is gone: this behaviour accounts for the failure. Restored text: 'run_visible=true; camel_user_visible=false; camel_agent_visible=false'. Evidence: f512d3ed-99f3-4b3b-91dc-08537e761bd0, 72370623-8987-41e3-a086-93f7b638e5a7, 683e2aa4-a508-4769-9292-16115d8e9a03, a1b27ace-c936-402e-93b2-9367124fae45, d8a5ba61-694f-4859-b9cd-6ad08f792256, ea401e67-1f52-4e13-8f99-c175b71b5c9d, a287d3df-f05b-4284-9d16-3c4eb7ddca24, 54f4b434-ccaa-4c4e-b75b-0baa314a28dd, 1d754ce5-0da2-43e2-9efd-d221fe382fde. Evidence: `f512d3ed-99f3-4b3b-91dc-08537e761bd0`, `72370623-8987-41e3-a086-93f7b638e5a7`, `683e2aa4-a508-4769-9292-16115d8e9a03`, `a1b27ace-c936-402e-93b2-9367124fae45` (+5 more)

## Evidence index

| Evidence | Kind | Run | Locator |
| --- | --- | --- | --- |
| `3e93020e-03ad-43a4-ab9d-98d72b9eced3` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `ccebff72-46df-45da-848e-61f9be63d52f` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/e95538aa-53df-4fb7-a358-2a85dc19d17e-sut-trace.json |
| `a944fe62-b0fc-439f-9b95-40c77857cd36` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `d522a4e8-b088-4137-9b02-f8b3453bc2c2` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `b0749830-32ff-47e7-b8ba-b9e34d721c64` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `9582bd16-0854-44f4-bcdb-8a7b9b851af9` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/7562677a-042f-4c0b-b93d-e93831d0b2e4-sut-trace.json |
| `1116651a-4f76-4494-bb66-270076945588` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `e1462f3e-867e-41a9-814c-806ee7434ac1` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `a0af75df-9e1f-4fc4-9dcc-2fd2b80695d6` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `76a7755b-316d-4512-9834-00a252913676` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/e632d05c-43b9-45b3-b05d-8eade920875b-sut-trace.json |
| `761b1399-ebd3-46d2-9518-a0b5780645a6` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `01b36de6-1902-4e73-ab4f-2287a6e7ccbe` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `79fb1625-35c2-4ce6-80f9-d148fc4ce617` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `99fbc668-b57f-400f-9f35-4e3c8b6acabf` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/891d0940-8429-449e-9978-1e0cbed04c94-sut-trace.json |
| `c8344f46-240b-4997-addd-70fb1b2f7782` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `a0548ba5-fb08-4b9c-a9e2-259d2b4adc3c` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `f512d3ed-99f3-4b3b-91dc-08537e761bd0` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `e905b108-7010-4e80-8417-3de53d59489f` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/e2ea5367-fb2e-4995-9007-a4d413aa6ff8-sut-trace.json |
| `74d5fed4-1356-4288-891f-d8459f6f9ed2` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `26b53d1a-2ab9-4b91-9b03-8eb6ed28dc8e` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `7e4fdf7a-d29f-4e02-b4ab-b8bb4810f032` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `3427f44e-d832-4285-8c70-80fbb7407254` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/774c6c5d-c080-47a8-9110-b5b9d75a87f4-sut-trace.json |
| `254eac9c-a0ff-4180-8918-e61a54d9c059` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `5a5b732c-fdf2-47c4-9f93-39e2317bd7cd` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `34fa7f50-c342-4594-bd40-ba922375d939` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/investigation-reference-corpus-cross-check.json |
| `64d8438e-8c1a-48a3-9e9a-604b340b4d56` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `1d7350d9-67c3-4c7e-aa63-b7fb9cd5c724` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/7562677a-042f-4c0b-b93d-e93831d0b2e4-sut-trace.json |
| `8613e2d6-415c-4b5d-973e-ee04de960613` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `5afe796e-c735-4bd1-982f-dda26eb939c9` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `293add00-0d3a-4130-8fd8-d6ddc4cbd2c0` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `1d7035c1-bb51-4d50-ae5b-a2a837a1118f` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/7562677a-042f-4c0b-b93d-e93831d0b2e4-sut-trace.json |
| `d9e72e87-fec6-4388-84ea-7f8fd2e5a038` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `be48d772-6648-4aea-b794-5b94f9c75aef` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `13dfb866-9517-460c-b05e-b6525a096af3` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `1d7a7f5b-3e3c-4e21-883d-75ae0be956d0` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/891d0940-8429-449e-9978-1e0cbed04c94-sut-trace.json |
| `95430109-cb7a-49dd-bf27-df20859ae3ed` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `b3835944-d231-454f-9d0d-30864e8792e5` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `174a6d23-7516-49d5-9fa4-ac57c5bce797` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `51456bf0-4a75-4a33-a880-45de122d19d8` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/891d0940-8429-449e-9978-1e0cbed04c94-sut-trace.json |
| `b07bc0ea-250e-44d9-bde9-4d4fae1494e1` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `3e9941cc-fee2-4b71-80d2-0458bacfb805` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `72370623-8987-41e3-a086-93f7b638e5a7` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `683e2aa4-a508-4769-9292-16115d8e9a03` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/774c6c5d-c080-47a8-9110-b5b9d75a87f4-sut-trace.json |
| `a1b27ace-c936-402e-93b2-9367124fae45` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `d8a5ba61-694f-4859-b9cd-6ad08f792256` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `ea401e67-1f52-4e13-8f99-c175b71b5c9d` | citation | `6862f691-d7aa-4294-b638-77a649ad2546` | mem0-identity-scope |
| `a287d3df-f05b-4284-9d16-3c4eb7ddca24` | trace | `6862f691-d7aa-4294-b638-77a649ad2546` | data/artifacts/6862f691-d7aa-4294-b638-77a649ad2546/774c6c5d-c080-47a8-9110-b5b9d75a87f4-sut-trace.json |
| `54f4b434-ccaa-4c4e-b75b-0baa314a28dd` | text | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |
| `1d754ce5-0da2-43e2-9efd-d221fe382fde` | metric | `6862f691-d7aa-4294-b638-77a649ad2546` | inline payload |

Every claim above cites evidence rows recorded during the run; each row carries the exact input, output and tool trace it was captured from.
