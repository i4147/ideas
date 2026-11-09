# 33 — `password-manager-cli` (local encrypted password store)

> **Difficulty 3/10** · **Effort ~4 days for something worse than `pass`** · **Tier: medium**
> **Prior art: ❌ solved by mature, audited tools** — `pass` (password-store, GPG + git), `kpxc`/`keepassxc-cli`, `gopass`, `himitsu`, `bitwarden-cli`, `1password-cli`, `sops`, `vault`.
> **Verdict: don't build.** Not because it's impossible, but because the failure mode is catastrophic and the existing tools have years of audits.

## Why this specific idea keeps appearing

It looks like the perfect CRUD project: store `{name: password}`, encrypt the file, add a master key. The gap between that and something safe is enormous:

- **Master key derivation**: you need Argon2id (or scrypt) with calibrated parameters, a persisted salt and parameter block, and a versioned header so future parameter increases don't brick old vaults.
- **AEAD with associated data**: the vault file must be authenticated (header included in the AAD) so an attacker can't downgrade the KDF parameters or swap ciphertexts between entries.
- **Memory hygiene**: Python can't reliably zero strings (`str` is immutable, GC copies). A "secure" manager in pure Python leaks the master password to swap and to core dumps. This is not theoretical — `mlock`/`madvise` from Python requires ctypes, and even then the interpreter holds copies.
- **Non-secret leakage**: search must not reveal which entries exist without decryption; clipboard must auto-clear; `--history` must not keep plaintext.
- **Concurrency and corruption**: two shells writing the vault, a crash mid-write, a partial sync through Dropbox — you need atomic replace + a backup + a checksum.
- **Recovery**: users forget master passwords. That means either a recovery key (another secret to manage) or data loss.

`pass` solves all of this by delegating crypto to GPG and history to git, in 900 lines of shell. `keepassxc-cli` delegates to an audited C++ core. `sops` delegates to age/KMS. There is nothing left to win.

## If someone in the group wants to build it anyway

Build the **components** as a library with tests, never claim it's a password manager:

1. `vault-format` — a documented, versioned file format (header, KDF params, salt, nonce, ciphertext, tag) with a spec document, test vectors, and a reference implementation using `cryptography` + `argon2-cffi`. Publish the spec; it's a writing/design exercise worth doing.
2. `pass-migrate` — a real gap: import/export between `pass`, KeePass XML, Bitwarden JSON, and 1Password CSV, *without* printing secrets, preserving folder structure and TOTP seeds. Migration between managers is genuinely painful and no CLI does all four.
3. `otp-cli` — RFC 6238 TOTP/HOTP generator that reads an `otpauth://` URI list and outputs codes; `oathtool` exists but has an awkward interface, and `pass otp` requires `pass`. Small, safe, useful.

## Non-negotiables if a prototype is built

`cryptography`'s `AESGCM` or `ChaCha20Poly1305` only (no self-made constructions, no `Fernet` with a password directly); Argon2id via `argon2-cffi`; a versioned magic header; `os.replace` for atomic writes; vault file mode `0600`; no secrets in argv (accept via stdin or prompt); clipboard clear after 20 s with a hash check; a `vault check` integrity command; and a loud README statement that it is not audited.

## Recommendation

Skip. Spend the slot on file 22 (shell history redaction), which handles the secrets people *actually* leak, or file 44 (secrets/config sync), which is where the real daily friction is.
