# Casino Digital Ledger v4

A persistent SQL-backed prototype for a casino digital value and forensic ledger.

## Main design
- SQLite is the default persistent SQL database: `casino_ledger_v4.db` beside `app.py`.
- WAL mode and transactional ledger posting are enabled.
- The ledger is append-oriented and hash chained; corrections should be represented as new events, not edits/deletes.
- Digital casino value is account-based. Token classes are CASHABLE, BONUS, TOURNAMENT and RESTRICTED.
- Cash settlement and token accounting are stored separately to reduce double counting.
- Player/admin/cage users cannot see tax screens. Only INVESTIGATOR can configure tax rules and generate statements.
- Taxable event types, rate, threshold, deduction and effective period are configurable and versioned.

## Demo credentials
- Player 1: `player1` / `player123`
- Player 2: `player2` / `player123`
- Cage: `cage` / `cage123`
- Admin: `admin` / `admin123`
- Investigator: `investigator` / `audit123`

## New player registration
The login screen contains a simple player registration form. It creates a player, token account, token balances and a player login. New registrations start as KYC=PENDING.

## Casino parameters covered
- KYC/player lifecycle and account status
- cashable/bonus/tournament/restricted value classes
- funding methods and settlement direction
- token issue/redemption
- table games, slots/EGMs, poker/tournament/jackpot game types
- game/session/round/bet lifecycle
- side bets, jackpot flag and payout allocations schema
- cage shifts and reconciliation
- compliance flags
- comps/tips/markers schema for future integration
- void/reversal schema for correction workflows
- unique event IDs and hash-chained audit trail
- investigator reconstruction and configurable tax basis

## Important production recommendation
Do not make this a public-blockchain cryptocurrency. The cost-effective production architecture is a centralized PostgreSQL event/ledger service integrated with cage, table-management, poker and slot systems. QR/NFC cards should identify the player/account; the balance remains on the central ledger. For high-value physical chips, serialized token/chip inventory can be enabled separately.

SQLite is appropriate for a demonstration/pilot. For concurrent casino deployment, migrate the same data model to PostgreSQL with proper API transactions, RBAC/MFA, maker-checker approval, immutable/WORM audit retention, backups/DR, centralized time and KMS/HSM controls.

**Tax rules in this prototype are configurable examples, not legal advice. Verify the applicable Indian tax law, rates, thresholds, deductions and reporting requirements before production use.**
