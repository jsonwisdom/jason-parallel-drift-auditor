# identity/

Purpose: hold replayable identity-claim envelopes and schemas without promoting labels, account surfaces, wallets, ENS names, or self-declarations into legal identity or authority.

## Invariants

```text
IDENTITY_LABEL != NATURAL_PERSON_IDENTITY
ENS_NAME != WALLET_OWNERSHIP
WALLET_CONTROL != LEGAL_IDENTITY
ACCOUNT_ASSOCIATION != AUTHORITY
AI_OUTPUT != PRIMARY_SOURCE
AUTHORITY_CREATED = FALSE
```

## Promotion order

```text
DECLARED_LABEL
  -> ACCOUNT_ASSOCIATION
  -> CONTROL_PROOF
  -> INDEPENDENT_PERSON_BINDING
  -> EXTERNAL_LAWFUL_AUTHORITY
```

Every edge requires its own receipt. Missing edges remain `HOLD`; conflicting receipts become `CONFLICT`.
