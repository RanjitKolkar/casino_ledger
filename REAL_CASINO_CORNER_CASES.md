# Real Casino Corner Cases / Requirements

## 1. Player lifecycle

A real system should support:
- walk-in registration
- repeat player login
- KYC incomplete
- KYC rejected
- suspended player
- self-exclusion
- duplicate identity
- lost credentials
- account closure
- multiple visits/sessions

## 2. Funding

Possible funding:
- cash cage
- card
- bank transfer
- UPI
- approved casino credit/marker

Every funding transaction should have:
- source
- amount
- payment reference
- cashier
- time
- approval
- settlement status

## 3. Digital token

Recommended production model:
- account-level balance for scalability
- optional individually serialised tokens for high-value chips

A token cannot:
- be created by a player
- be duplicated
- move without an event
- be redeemed twice

## 4. Table games

A round can contain:
- one player
- many players
- one winner
- many winners
- no winner
- tie/draw
- side-bet winners
- jackpot winner
- shared jackpot

Example:

Round R100:
A stakes 10,000
B stakes 5,000
C stakes 5,000

A wins 12,000
B wins 6,000
C loses

All three records belong to the same round.

## 5. Poker

Poker needs different accounting:
- buy-in
- rebuy
- add-on
- pot
- rake/house fee
- side pot
- multiple winners
- prize distribution

Do not force poker into a simple "bet → payout" model.

## 6. Tournament

Record:
- registration
- entry fee
- rebuy
- prize pool
- house share
- ranking
- prize allocation
- multiple winners

## 7. Slots / EGM

Use:
- machine ID
- player session
- spin/round number
- wager
- payout
- jackpot meter
- machine opening/closing meter

## 8. Voids and errors

If a dealer accidentally records ₹10,000 instead of ₹1,000:
- do not edit the old record
- create a correction
- link correction to original event
- require supervisor approval

## 9. Token/cage reconciliation

At shift close:
Opening float
+ issued value
- redeemed value
± transfers
= expected closing value

Compare against physical/digital inventory.

## 10. Investigator reconstruction

Investigator should be able to answer:

"Show me everything associated with Player PLR-1001 on 5 October."

The result should include:
KYC
funding
token issue
games
tables
rounds
bets
wins
jackpots
transfers
redemptions
settlements
corrections
audit events

without requiring the casino to manually prepare a report.

## 11. Tax

Tax should be a derived compliance layer.

Player and casino management should not have a tax dashboard in this application.

Investigator can:
- select player
- select period
- derive qualifying winnings
- apply the versioned rule
- generate statement
- retain statement reference
- export evidence

## 12. Security

Production must add:
- MFA
- SSO
- RBAC
- encryption at rest
- TLS
- database encryption
- HSM/KMS
- signed events
- immutable/WORM logs
- backups
- disaster recovery
- maker-checker
- privileged access monitoring
