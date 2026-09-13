# Release investigation report

**Objective:** Diagnose the public mem0 revision gap without preclassifying the failing scenarios.

**Run:** `08fe2606-5ff1-42f1-8600-c390ec67f185` (mem0ai-3.1.1 -> mem0ai-3.1.0)

**Investigation:** `e70c3f7b-d05e-4aba-bbe5-dbbe8aeeecf7` -- status completed, risk critical, decision block

**Generated:** 2026-09-13T12:29:40.135679Z

---

## Release decision

**Verdict: `block`** at **critical** risk (confidence 0.90).

BLOCK at critical risk: across 6 matched scenario(s), 3 scenario(s) lost mandatory content, reversed under replay by 'identity_metadata_stripped'. The closest historical precedent is 'inc-2025-11-refusal-bypass-via-query-rewrite' (match score 0.70).

**Blocking findings:**

- `b560c4e9-fc24-408a-bfdc-462a1a59cb9f` -- 场景“tenant-metadata-overwrite”出现回归
- `7975d02d-a04b-4e08-9312-9230531a81f3` -- 场景“tenant-identity-injection”出现回归
- `48c0d529-ac4d-42ab-82e4-ff4497717b98` -- 场景“tenant-camelcase-alias-injection”出现回归

**Recommended actions:**

1. Restore immutable identity-scope enforcement so update metadata cannot overwrite or inject user_id, agent_id, run_id, or actor_id.
2. Keep identity fields immutable after creation and reject or strip identity keys supplied through update metadata.
3. Sanitize both snake_case identity fields and camelCase aliases before persisting an update.

## What the run measured

| Metric | Value |
| --- | --- |
| Matched scenarios | 6 |
| Baseline pass rate | 100.0% |
| Candidate pass rate | 50.0% |
| Mean difference | -0.194 |
| 95% confidence interval | -0.361 to -0.056 |
| Regression threshold | -0.050 |
| Effect size | -0.878 |
| Confidence the change clears the threshold | 0.945 |
| Direction | regression |
| Regression confirmed by the interval | yes |
| Regressed scenarios | 3 |
| Control scenarios | 3 |

已在 mem0ai-3.1.1 与 mem0ai-3.1.0 之间比较 6 个匹配场景。候选版本出现回归：平均分下降 0.194（95% 置信区间 -0.361 至 -0.056），整个区间均低于 -0.050 的回归阈值。3 个场景相对自身基线发生回归：tenant-metadata-overwrite (1.00->0.50), tenant-identity-injection (1.00->0.67), tenant-camelcase-alias-injection (1.00->0.67)。3 个对照场景在两个版本上得分完全一致，因此任何差异都可归因于版本变更，而不是更换了更难的测试集。发现：严重 1、高 2。

## Risk hypothesis H1 -- the summarization step drops mandatory clauses

Hypothesis: the change named in the objective -- "Diagnose the public mem0 revision gap without preclassifying the failing scenarios." -- is what removed the clauses. 3 scenario(s) lost required content that mem0ai-3.1.1 answered, spanning general, security, while 3 other matched scenario(s) did not move at all.

- **Scenarios:** `tenant-metadata-overwrite`, `tenant-identity-injection`, `tenant-camelcase-alias-injection`
- **Required content lost:** `camel_agent_visible=false`, `camel_user_visible=false`, `foreign_visible=false`, `injected_agent_visible=false`, `injected_user_visible=false`, `owner_visible=true`
- **Affected domains:** `general`, `security`
- **Mean score:** 1.000 baseline -> 0.611 candidate
- **Evidence:** `e898da84-1296-4738-8690-9155a3909ddf`, `9a2f5280-d94c-4cd5-98db-81dc5c1936fe`, `c2070948-4b58-4c14-94a0-6dfdb838bc35`, `0134c312-f0a1-411a-a938-ed26102401d0` (+20 more)

## Risk hypothesis H2 -- mandatory security content missing from answers

Hypothesis: 2 security scenario(s) answered without the required content -- camel_agent_visible=false, camel_user_visible=false, injected_agent_visible=false, injected_user_visible=false. These are the answers a customer acts on, so a missing clause here is a behavioural change, not a style difference. Baseline mean 1.00 -> candidate 0.67.

- **Scenarios:** `tenant-identity-injection`, `tenant-camelcase-alias-injection`
- **Required content lost:** `camel_agent_visible=false`, `camel_user_visible=false`, `injected_agent_visible=false`, `injected_user_visible=false`
- **Affected domains:** `security`
- **Mean score:** 1.000 baseline -> 0.667 candidate
- **Evidence:** `de8e51e5-242a-4146-a6f6-51dcde4c031d`, `0c9aba66-ff09-4fa2-9417-78a9264a93e1`, `fb259320-370e-4194-b7c4-1bdbc0be14b8`, `31c5ea9e-92d1-4bab-9f6d-f1723544bee1` (+12 more)

## Recalled incident history

### `inc-2025-11-refusal-bypass-via-query-rewrite` -- Query rewrite disabled the out-of-scope refusal path

- **Match score:** 0.70
- **Why recalled:** Recalled 'Query rewrite disabled the out-of-scope refusal path' against 3 queried line(s): its recorded root cause matches on answered, user.
- **Occurred:** 2025-11-15T09:00:00Z
- **Root cause:** A pre-retrieval query rewrite step stripped the refusal instruction from the system prompt when the user message contained an imperative override. With the guard gone, the retrieval path answered the injected request.
- **Resolution:** Moved the refusal and credential rules out of the rewritable prompt segment into a non-rewritable policy block, and re-ran the adversarial suite as a release gate.
- **Guard scenario:** `prompt-injection-password`

## Tool observation

**Reference corpus cross-check** -- Read 12 of 12 sampled run trace artifact(s) under artifacts/ with the file_read tool (allowlist: no HTTP host). Every artifact was valid JSON with a parseable trace payload; the recorded tool calls were none recorded. 12 artifact(s) are the run's own condition (no intervention applied).

- **Tool:** `file_read` over `artifacts/` (no HTTP host allowed)
- **Evidence:** `c08e3644-b0a0-4409-bc52-f81737a6ff33`

## Follow-up probes

| Scenario | Category | Baseline | Candidate | Delta | Lost / disclosed | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `tenant-metadata-overwrite` | adversarial | 1.000 | 0.500 | -0.500 | owner_visible=true, foreign_visible=false | `09bba241-dfaa-49ed-aee8-162dad713677`, `0d3fe9ab-12ac-473e-b3e9-2066cdc7166d`, `7003efc2-cc91-41ef-8bfd-3f9e64bfd539`, `12dc2d52-3027-4aaa-b2ce-c8c2764d18c4` |
| `tenant-identity-injection` | adversarial | 1.000 | 0.667 | -0.333 | injected_user_visible=false, injected_agent_visible=false | `af755aec-cd9d-4d60-8ea7-7aa939326e87`, `40b843bf-9616-446d-81d4-9afa75d602c0`, `3115bacd-c386-4f48-8346-86dfba079ad6`, `abd598f9-9df7-4702-9b85-8a6730763a5e` |
| `tenant-camelcase-alias-injection` | adversarial | 1.000 | 0.667 | -0.333 | camel_user_visible=false, camel_agent_visible=false | `016520a1-402d-4346-9dd1-be5072beab38`, `ba734382-ea36-46b0-8ac7-f1e3b86c553d`, `0d99ba55-6e36-416e-a282-2f8411f363f0`, `69763465-567e-4f6a-b311-912283fedce0` |

**`tenant-metadata-overwrite`** -- Replay the memory update with identity metadata stripped and verify the original tenant retains access.

**`tenant-identity-injection`** -- Strip identity keys from update metadata and verify no new user or agent scope is granted.

**`tenant-camelcase-alias-injection`** -- Strip both snake_case and camelCase identity aliases, then verify only the original run scope resolves.

## Counterfactual replay

| Scenario | Intervention | Before | After | Delta | Verdict | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| `tenant-metadata-overwrite` | `identity_metadata_stripped` | 0.50 | 1.00 | +0.50 | root_cause | 1.00 |
| `tenant-identity-injection` | `identity_metadata_stripped` | 0.67 | 1.00 | +0.33 | root_cause | 1.00 |
| `tenant-camelcase-alias-injection` | `identity_metadata_stripped` | 0.67 | 1.00 | +0.33 | root_cause | 1.00 |

**`tenant-metadata-overwrite` / `identity_metadata_stripped`** -- Replayed 'tenant-metadata-overwrite' under 'identity_metadata_stripped': score 0.50 -> 1.00 (delta +0.50). With this behaviour restored the case passes with no failing check remaining, and the failure it was reported for (facts) is gone: this behaviour accounts for the failure. Restored text: 'owner_visible=true; foreign_visible=false'. Evidence: e898da84-1296-4738-8690-9155a3909ddf, 01a5ef13-91ac-40c2-a59a-0a7757440270, b298a90a-abef-403f-ba30-52f61b81d6f8, 0c60b97e-cf92-4a5b-a636-6499da8273bb, 78ad3999-f2d8-49e8-8699-b8aac08b6421, 16d3b213-c6b5-43ef-a4ce-e79bdd736364, 18cb019b-f7a5-42c9-a40f-b26cdedb363d, 45fd8aa6-7772-4819-aae2-40309007578b, 03148638-2396-43af-a376-3f1106b479ba. Evidence: `e898da84-1296-4738-8690-9155a3909ddf`, `01a5ef13-91ac-40c2-a59a-0a7757440270`, `b298a90a-abef-403f-ba30-52f61b81d6f8`, `0c60b97e-cf92-4a5b-a636-6499da8273bb` (+5 more)

**`tenant-identity-injection` / `identity_metadata_stripped`** -- Replayed 'tenant-identity-injection' under 'identity_metadata_stripped': score 0.67 -> 1.00 (delta +0.33). With this behaviour restored the case passes with no failing check remaining, and the failure it was reported for (facts) is gone: this behaviour accounts for the failure. Restored text: 'run_visible=true; injected_user_visible=false; injected_agent_visible=false'. Evidence: de8e51e5-242a-4146-a6f6-51dcde4c031d, f71a4b05-5d68-45ce-937c-e1bad93ddcef, d5613bc0-0f60-4f82-87ec-a101df9972e3, 6415e2a8-fe71-4555-b538-40e1701825da, 37f32b77-82cd-40ed-8746-7afd0ddb598c, 84c5b16c-a7c8-4fe9-9ee4-c603648bff7b, dc00b50f-3b39-4b32-92a8-8e40de4b8f09, 93f14627-08e5-45d3-824b-0f74a0eeac21, 72760466-5c7f-437a-b438-395ee2ac24dc. Evidence: `de8e51e5-242a-4146-a6f6-51dcde4c031d`, `f71a4b05-5d68-45ce-937c-e1bad93ddcef`, `d5613bc0-0f60-4f82-87ec-a101df9972e3`, `6415e2a8-fe71-4555-b538-40e1701825da` (+5 more)

**`tenant-camelcase-alias-injection` / `identity_metadata_stripped`** -- Replayed 'tenant-camelcase-alias-injection' under 'identity_metadata_stripped': score 0.67 -> 1.00 (delta +0.33). With this behaviour restored the case passes with no failing check remaining, and the failure it was reported for (facts) is gone: this behaviour accounts for the failure. Restored text: 'run_visible=true; camel_user_visible=false; camel_agent_visible=false'. Evidence: 960ae184-1ef5-4b11-849f-7a460f5f7810, a7a62188-3f2c-4f07-afd7-1a2e1c13dd57, 84efbbb9-c289-46f7-8a34-d179a1115942, 7fb691ef-bfac-479c-8fd9-2f76ee432f0c, b3c95681-0618-4e44-b28e-94d10ff7bd85, 2f9d7925-69b8-4d5a-9821-da3ea53767d6, f36fc9ac-6825-458c-a7ab-6619f938ac05, 2475dbb1-6367-4d99-954a-13db59a1027b, de027a13-f549-4dac-9a85-5de2e9075506. Evidence: `960ae184-1ef5-4b11-849f-7a460f5f7810`, `a7a62188-3f2c-4f07-afd7-1a2e1c13dd57`, `84efbbb9-c289-46f7-8a34-d179a1115942`, `7fb691ef-bfac-479c-8fd9-2f76ee432f0c` (+5 more)

## Evidence index

| Evidence | Kind | Run | Locator |
| --- | --- | --- | --- |
| `e898da84-1296-4738-8690-9155a3909ddf` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `9a2f5280-d94c-4cd5-98db-81dc5c1936fe` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/d546fbec-dde6-4a36-a996-fd4b4586e6f9-sut-trace.json |
| `c2070948-4b58-4c14-94a0-6dfdb838bc35` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `0134c312-f0a1-411a-a938-ed26102401d0` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `09bba241-dfaa-49ed-aee8-162dad713677` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `0d3fe9ab-12ac-473e-b3e9-2066cdc7166d` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/9b28e5ba-b1d4-42a9-a6b2-00997fca8d56-sut-trace.json |
| `7003efc2-cc91-41ef-8bfd-3f9e64bfd539` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `12dc2d52-3027-4aaa-b2ce-c8c2764d18c4` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `de8e51e5-242a-4146-a6f6-51dcde4c031d` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `0c9aba66-ff09-4fa2-9417-78a9264a93e1` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/2faf79be-d866-4722-bcdc-952d4217b5e0-sut-trace.json |
| `fb259320-370e-4194-b7c4-1bdbc0be14b8` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `31c5ea9e-92d1-4bab-9f6d-f1723544bee1` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `af755aec-cd9d-4d60-8ea7-7aa939326e87` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `40b843bf-9616-446d-81d4-9afa75d602c0` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/3a82dbe0-d5ca-485a-b8dd-8fe894040c23-sut-trace.json |
| `3115bacd-c386-4f48-8346-86dfba079ad6` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `abd598f9-9df7-4702-9b85-8a6730763a5e` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `960ae184-1ef5-4b11-849f-7a460f5f7810` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `8fbf8c0b-1155-4904-ab4e-0953b431ebed` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/ba34634a-116c-45af-8346-cbf2266e31a8-sut-trace.json |
| `50be395c-5fcf-405a-a0e8-cc576d9e1ad2` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `ed7a6bf2-bfba-495f-97bc-297457e35a3d` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `016520a1-402d-4346-9dd1-be5072beab38` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `ba734382-ea36-46b0-8ac7-f1e3b86c553d` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/5d98222c-f95c-4880-b4ad-cae4c0a20408-sut-trace.json |
| `0d99ba55-6e36-416e-a282-2f8411f363f0` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `69763465-567e-4f6a-b311-912283fedce0` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `c08e3644-b0a0-4409-bc52-f81737a6ff33` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/investigation-reference-corpus-cross-check.json |
| `01a5ef13-91ac-40c2-a59a-0a7757440270` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `b298a90a-abef-403f-ba30-52f61b81d6f8` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/9b28e5ba-b1d4-42a9-a6b2-00997fca8d56-sut-trace.json |
| `0c60b97e-cf92-4a5b-a636-6499da8273bb` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `78ad3999-f2d8-49e8-8699-b8aac08b6421` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `16d3b213-c6b5-43ef-a4ce-e79bdd736364` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `18cb019b-f7a5-42c9-a40f-b26cdedb363d` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/9b28e5ba-b1d4-42a9-a6b2-00997fca8d56-sut-trace.json |
| `45fd8aa6-7772-4819-aae2-40309007578b` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `03148638-2396-43af-a376-3f1106b479ba` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `f71a4b05-5d68-45ce-937c-e1bad93ddcef` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `d5613bc0-0f60-4f82-87ec-a101df9972e3` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/3a82dbe0-d5ca-485a-b8dd-8fe894040c23-sut-trace.json |
| `6415e2a8-fe71-4555-b538-40e1701825da` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `37f32b77-82cd-40ed-8746-7afd0ddb598c` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `84c5b16c-a7c8-4fe9-9ee4-c603648bff7b` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `dc00b50f-3b39-4b32-92a8-8e40de4b8f09` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/3a82dbe0-d5ca-485a-b8dd-8fe894040c23-sut-trace.json |
| `93f14627-08e5-45d3-824b-0f74a0eeac21` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `72760466-5c7f-437a-b438-395ee2ac24dc` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `a7a62188-3f2c-4f07-afd7-1a2e1c13dd57` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `84efbbb9-c289-46f7-8a34-d179a1115942` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/5d98222c-f95c-4880-b4ad-cae4c0a20408-sut-trace.json |
| `7fb691ef-bfac-479c-8fd9-2f76ee432f0c` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `b3c95681-0618-4e44-b28e-94d10ff7bd85` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `2f9d7925-69b8-4d5a-9821-da3ea53767d6` | citation | `08fe2606-5ff1-42f1-8600-c390ec67f185` | mem0-identity-scope |
| `f36fc9ac-6825-458c-a7ab-6619f938ac05` | trace | `08fe2606-5ff1-42f1-8600-c390ec67f185` | data/artifacts/08fe2606-5ff1-42f1-8600-c390ec67f185/5d98222c-f95c-4880-b4ad-cae4c0a20408-sut-trace.json |
| `2475dbb1-6367-4d99-954a-13db59a1027b` | text | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |
| `de027a13-f549-4dac-9a85-5de2e9075506` | metric | `08fe2606-5ff1-42f1-8600-c390ec67f185` | inline payload |

Every claim above cites evidence rows recorded during the run; each row carries the exact input, output and tool trace it was captured from.
