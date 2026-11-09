# 14 — `file-encryptor` (password-based file encryption)

> **Difficulty 2/10** · **Effort ~half a day** · **Tier: warm-up**
> **Prior art: ❌ fully solved by better tools** — `age` (0.5.1, PyPI bindings + Go binary), `gpg`, `openssl enc`, `rclone crypt`, Python `cryptography`'s `Fernet`, `pass`.
> **Verdict: do not build.** Cryptography tooling written as a learning project is how data gets lost or leaked.

## Why this is a bad idea specifically

AES-256 file encryption looks like a weekend project (`cryptography.fernet` is four lines) and is a decade-long liability:

- **Nonce/IV reuse** under the same key is a total break. Hand-rolled streaming encryption gets this wrong constantly.
- **Authentication**: without an AEAD (GCM/ChaCha20-Poly1305) or an encrypt-then-MAC construction, ciphertext is malleable.
- **Key derivation**: users will type a password. You need Argon2id or scrypt with sane parameters, plus a stored salt and parameters version — and you need to get the versioning right forever.
- **Streaming + chunking** for large files, with per-chunk nonces, final-chunk marking, and truncation detection.
- **File format compatibility** matters more than anything: if your format is only readable by your tool, you've created a data-loss trap.

`age` exists precisely because this is hard, is audited, has a 4-line format spec, supports passphrase mode (`age -p`) and X25519 recipients, and can stream. `age` also has a Python binding (`pyage`/`rage`), and `cryptography` ships `Fernet` for the "just obfuscate this token" case.

## What to build instead, if the interest is real

Pick one of these, which are *not* solved:

1. **`secret-share`** — split a file into N-of-M shares (Shamir over GF(256)) with a documented, tested format, so three people must cooperate to recover a recovery key. `shamirs` exists as a library; no good CLI with file framing and verification.
2. **`age-rotate`** — re-encrypt a directory of `age`-encrypted files to new recipients, verifying each plaintext round-trip and writing a rollback manifest. Real operational gap: `age` has no rotation workflow.
3. **`encfs-audit`** — scan a directory for files that *look* encrypted (high entropy, no magic bytes) but were never backed up with their key, and report the ones at risk. Odd but genuinely unserved.

## If you insist on building the original

Non-negotiables: use `cryptography`'s `AESGCM`/`ChaCha20Poly1305` with 256-bit random key per file wrapped by a KDF-derived key; Argon2id via `argon2-cffi` (m=64 MiB, t=3, p=4) with parameters stored in the header; a versioned header (`MAGIC\0`, version, KDF id, params, salt, wrapped-key nonce, wrapped key); 1 MiB chunks each with its own nonce and an AAD of the chunk index; and a `--verify` mode that decrypts to `/dev/null` and checks the auth tag. Test with Wycheproof-style vectors and a corrupt-every-byte fuzz test.

## Recommendation

Spend the slot elsewhere (see files 34, 46, 57, 70). Encryption is the one category where "it works" is not the bar.
