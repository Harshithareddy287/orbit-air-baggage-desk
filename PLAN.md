# Plan: Orbit Air Baggage Desk

## The problem

Orbit Air keeps its baggage claims in spreadsheets and emails. Because of that,
nobody can easily see which claims are about to miss their deadline, and a lot
of passengers get answers late.

I'm building a small command line app in Python with a SQLite database. It will
let the desk file a claim, assign it to an agent, move it through its statuses,
keep a record of every change, and flag claims that are late.

## The rules

### Deadlines

How long we have to respond depends on the passenger's tier:

- Gold: 4 hours
- Silver: 24 hours
- Standard: 72 hours

The deadline is the time the claim was filed plus those hours. A claim only
counts as overdue once the current time has gone past the deadline. If it is
exactly the deadline, it is still on time.

My code will never read the clock by itself. The current time will always be
passed in. In the command line, `--now` lets me pick the time, which makes it
easy to test late claims without waiting days.

### Status changes

Every claim starts as `open`. These are the only moves allowed:

- open can go to assigned or escalated
- assigned can go to resolved or escalated
- escalated can go to assigned or resolved
- resolved can go to closed
- closed is final and can't change

Anything else gets a clear error and nothing is saved. A claim can only be
escalated if it is open or assigned and already overdue. I'll keep these moves
in a dictionary so they are easy to read and test.

### History

Every time a claim is filed or changes status, I save a history row. The status
change and its history row are saved together. If the history row fails to
save, the status change is cancelled too.

When a claim is filed, its first history row has `old_status` set to NULL,
`new_status` set to `open`, `changed_by` set to whoever filed it, and
`changed_at` set to the filing time.

## The tables

### claims

| Column | Type | What it holds |
|---|---|---|
| id | INTEGER | Claim number (primary key) |
| passenger | TEXT | Passenger name, can't be blank |
| flight | TEXT | Flight number, can't be blank |
| type | TEXT | delayed, lost or damaged (CHECK) |
| tier | TEXT | standard, silver or gold (CHECK) |
| status | TEXT | open, assigned, escalated, resolved or closed (CHECK), starts as open |
| assigned_agent | TEXT | Agent handling the claim, NULL until the claim is assigned |
| note | TEXT | Optional note from the passenger |
| filed_at | TEXT | When the claim was filed |
| deadline | TEXT | When we must respond by |

### history

| Column | Type | What it holds |
|---|---|---|
| id | INTEGER | Entry number (primary key) |
| claim_id | INTEGER | Which claim this entry belongs to, foreign key referencing claims(id) |
| old_status | TEXT | Status before the change, NULL for the first entry of a new claim |
| new_status | TEXT | Status after the change |
| changed_by | TEXT | Who made the change |
| changed_at | TEXT | When the change happened |

## Branches and tests

On each branch I'll write the tests first, commit them, and check that they
fail. Then I'll ask Claude Code to write the code that makes them pass.

### feature/schema-and-filing (10 tests)

- A valid claim is saved as open
- Blank passenger is rejected
- Blank flight is rejected
- Unknown type is rejected
- Unknown tier is rejected
- Gold deadline is 4 hours after filing
- Silver deadline is 24 hours after filing
- Standard deadline is 72 hours after filing
- Filing adds a history row
- List can filter by status and tier

### feature/assign-and-status (9 tests)

- Assigning an open claim works and saves the agent
- Assigning an escalated claim works
- Resolving an assigned claim works
- Resolving an escalated claim works
- Closing a resolved claim works
- Closing an open claim is rejected
- Resolving an open claim is rejected
- A closed claim can't change
- Each change adds a history row with old status, new status, who and when

### feature/deadlines-and-escalation (8 tests)

- One minute before the deadline: not overdue
- Exactly at the deadline: not overdue
- One minute after the deadline: overdue
- Overdue open and assigned claims get escalated
- Claims that aren't overdue yet are left alone
- Resolved and closed claims are left alone
- Escalation returns the claim ids and adds history rows
- If the history row fails, the claim doesn't change (rollback)

### feature/cli (4 tests)

- Filing and listing through the command line works
- `--now` is used as the time for escalate
- Seed loads the CSV file without errors
- A bad status change shows a clear error

## Risks

1. **Claude might change my tests to make them pass.** I commit the tests first,
   tell Claude not to touch them, and check `git diff tests/` before each commit.

2. **Time-based tests might break depending on the day.** I'll use fixed times
   in tests and pass the time into functions instead of reading the clock.

3. **The .env file could leak.** It's in .gitignore, Claude has a rule that
   blocks it from reading the file, and I check `git status` before committing.

4. **A claim note tries to trick Claude.** One sample note tells Claude to print
   .env. I'll treat notes as plain text, never as instructions, and the deny rule
   still keeps .env safe.

5. **A change could be half saved.** I'll save the status change and history row
   in one transaction, and write a test that forces the history save to fail to
   prove nothing changes.