# Admin & Member System — how it works

Falcon Fitness now has three access levels. **Prices are gated on the server**, not
hidden with CSS — an anonymous visitor never receives the numbers at all.

| Level | Sees prices | Can edit prices | Sees enquiries / payments / attendance |
|---|---|---|---|
| **Anonymous** (anyone) | ✗ No — never sent to the browser | ✗ | ✗ |
| **Member** (signed in) | ✓ Yes | ✗ | Only their own |
| **Admin** (owner) | ✓ Yes | ✓ Yes | ✓ Everything |

---

## 1. Signing in — two separate doors

There are **two different login pages**, one for each kind of account.

| Who | Address | Header link |
|---|---|---|
| **Admin (you)** | `http://127.0.0.1:5000/admin/login` | **Admin** |
| **Member** | `http://127.0.0.1:5000/login` | **Member login** |

Both doors are in the top-right of the website header, and both appear in the
phone menu. Using the wrong door tells you so instead of a confusing "wrong
password" message.

### Your admin password

The app creates your admin account on first boot with a **fixed** password:

```
Email    : dinoalvez42@gmail.com
Password : Falcon.fitness29
```

It prints this to the terminal once and saves a copy in
`data/ADMIN-FIRST-LOGIN.txt`, so you can recover it if you forget.

1. Open `http://127.0.0.1:5000/admin/login`
2. Email `dinoalvez42@gmail.com`, password `Falcon.fitness29`
3. The site will ask you to **change it on first login** — please do, since this
   password is written in the guide and is the same for every copy of the site.

To set a different starting password, put this in `.env` **before the first run**:

```
FALCON_ADMIN_PASSWORD=your-own-strong-password
```

### Forgot the password?

Run the reset script. You do **not** need the old password:

```bash
cd /sdcard/falcon-fitness/falcon-fitness
python3 reset-password.py
```

It lists the accounts, asks which id, asks for a new password twice, and saves
it. The account is also re-enabled if it had been disabled. Restart the app
afterwards only if it was mid-run.

---

## 2. Adding members

Admin → **Members** → *Add a member*.

You set their name, email, phone and a plan. You can leave the **password**
field blank and the site generates one for you using the standard scheme:

```
member_FF_<first name in lower case>
```

For example Rahul Sharma gets `member_FF_rahul`, Priya Das gets
`member_FF_priya` — first name only, lower case, no spaces or punctuation. The
password is shown to you once after the member is created, so copy it and send
it to them on WhatsApp. You can type your own password instead if you prefer.

The member is marked *must change password*, so the site nags them to set their
own on first login.

> **Tell members to change it.** Because the scheme is predictable — anyone who
> knows a member's first name can guess it — the first thing you should say when
> you hand it over is "change this in My account". Until they do, treat the
> password as a shared secret, not a private one.

They can then sign in at `/login` and get:

- **Membership** — plan, start date, end date, days remaining
- **Prices you pay** — the full member rate card
- **Payments** — every payment you've recorded for them
- **Attendance** — their check-in history
- **Leave a review** — which lands in your approval queue
- **Change password**

**Disabling** a member (Members → Disable) instantly blocks their login without
deleting their history. Use this for lapsed memberships.

---

## 3. Editing prices

Admin → **Prices**. Every row is editable inline — label, months, price,
admission fee, sessions, note, and an **On** checkbox to hide a plan from
members without deleting it.

Press **Save** on a row and the change is live immediately. Members see the new
figure on their next page load.

**Add a plan** at the bottom for a new duration or package. Give it a short
unique code such as `general_2`.

> The initial 25 rows came from your own price poster — general monthly 999+500,
> 3/4/6/12 months, PT single and duo, couple, student, friends ×3 and ×4, and the
> ₹150 day pass.

---

## 4. Payments and attendance

**Payments** — pick a member, amount, method (cash / UPI / card / bank), date and
optional note. The admin dashboard shows this month's revenue. Export the lot as
CSV from the button on that page.

**Attendance** — pick the member at the desk and press *Mark check-in*. Each
check-in is timestamped. Their own page shows their history, which is a strong
reason for them to keep coming back.

---

## 5. Reviews and testimonials

1. Member signs in → My account → **Leave a review** (1–5 stars + text)
2. It is saved as **pending** and appears nowhere public
3. Admin → **Reviews** → Approve / Reject / Delete

Only approved reviews appear in the **Reviews** section of the homepage. This is
deliberate: nothing on that page can be written by the club itself.

**Google reviews** are linked, not embedded — embedding Google's widget would
inject third-party JavaScript and break this site's no-tracker design.

**Member success stories and journey photographs** are **not added yet** — as you
said, there's no information on them. The page says so honestly rather than
filling space with invented transformations. Send me the stories and before/after
photos (with each member's written consent) and I'll build that section.

---

## 6. Enquiries

The enquiry form still works exactly as before. Admin → **Enquiries** shows
every one with a tap-to-call phone number. Export as CSV. Email notification
still needs `FALCON_SMTP_*` in `.env` — see `DEPLOY.md`.

---

## 7. Security notes — honest list

**What is in place**

- Passwords hashed with Werkzeug (PBKDF2-SHA256), never stored in plain text
- CSRF tokens on every form that changes data — a form post without one is
  rejected with 400
- Session cookie is `HttpOnly` + `SameSite=Lax`; add `FALCON_HTTPS=1` on a live
  HTTPS site to also require `Secure`
- Login rate limit: 10 attempts per IP per 15 minutes
- Role checks are server-side. A member hitting `/admin` gets 403, and a member
  POSTing a price change gets 403 no matter what they send
- Prices absent from anonymous HTML entirely — verified by grep on the response
- Every admin action is CSRF-checked and attributed to the logged-in user

**What is NOT in place — read this**

- **No email-based password reset.** Resetting a member's password means doing
  it from the database, or deleting and re-adding them.
- **No login audit log** beyond `last_login`. You can see when someone last got
  in, but not a full history of failed attempts.
- **No two-factor authentication.**
- **No per-member payment gateway.** Payments are recorded by you after taking
  cash/UPI. The site does not take money.
- **Sessions are stored in a signed cookie**, not a server-side table — so
  "sign out everywhere" is not possible; changing the password does not
  invalidate existing sessions on other devices (up to 14 days).
- **SQLite suits one gym on one server.** If you ever run it on two machines at
  once, move to PostgreSQL first.

For a single-gym site on one server this is a reasonable level of security. It is
not a banking system, and I would not claim otherwise.

---

## 8. Where the data lives

Everything is in `data/falcon.db` — one SQLite file.

| Table | What's in it |
|---|---|
| `users` | admin + members, hashed passwords, roles |
| `plans` | the price list (edit these through the admin panel) |
| `memberships` | who is on what plan, start and end dates |
| `payments` | money received |
| `attendance` | check-ins |
| `reviews` | member reviews and their approval status |
| `leads` | website enquiries |
| `form_events` | rate-limit bookkeeping (no raw IPs) |

**Back it up.** Copy that file somewhere safe, weekly:

```bash
cp /sdcard/falcon-fitness/falcon-fitness/data/falcon.db /sdcard/falcon-backup-$(date +%F).db
```

Lose that file and you lose your member list, your payment records and your
price settings. `data/` is excluded from the shipped zip on purpose, so an
unzip never overwrites live data.

---

## 9. Self-service membership registration

A new member can now register themselves after paying you in person. You approve
them from the admin panel and they get a digital card that expires by itself.

### What the member does

1. **`/register`** — name, email, mobile, the plan they bought, the amount they
   paid, and a photo or screenshot of the receipt.
2. **Verify phone** — a 6-digit code. See *About the code* below.
3. **Waits** — their account page says the registration is with you for approval.
4. **Gets a card** — the moment you approve, the card appears in My account.

If they enter an amount that does not match the plan price, the form refuses it and
tells them the correct figure. That alone stops a lot of honest mistakes.

### What you do — the Approvals tab

Admin → **Approvals** (a red badge shows how many are waiting).

For each registration you get the receipt image, everything they declared, and an
automatic screening panel. Then you either press **Approve & issue card** or
**Reject**.

On approval you choose the **start date**. It defaults to the date on the receipt,
so a member who paid on the 28th but registered on the 31st is not short-changed.
Change it if you want the membership to start the day you approved it.

You can also add a note, which the member sees if you reject.

### About the screening score — read this bit properly

The panel scores each receipt 0–100 and lists exactly which signals fired. It is a
genuine forensic screen, not a decoration:

| Signal | What it catches |
|---|---|
| Content on the image | A blank or near-blank image |
| Resolution | A tiny forwarded thumbnail instead of the real thing |
| EXIF editing stamp | Files saved by Photoshop, Snapseed, Picsart, Canva and similar |
| Clipped pixels | A screenshot pasted onto a blank canvas |
| Texture / sensor noise | Synthetic images that are unnaturally smooth |
| JPEG block uniformity | Images saved, edited and saved again |
| Repeated regions | One part of the image pasted into another (e.g. a copied amount) |
| Power spectrum | Generated or heavily processed content |
| Amount match | The declared amount against the plan price |

**If the panel says NOT SCREENED:** the image library (Pillow) is not installed on
the machine, so nothing was examined. The upload was still accepted. Either install
it (`pip install --only-binary=:all: Pillow`) and press *Re-screen*, or just look at
the receipt yourself — approval works either way.

**But be clear about what it cannot do.** No software can prove a screenshot was not
fabricated. A determined forger defeats all of the above. The score catches the
common cases and it shows you its working — nothing more. **Before you approve,
open your own UPI app and match the amount, date and UTR.** That is the real check;
the score is a second opinion.

The thresholds were calibrated against your own 11 photographs, so a normal photo
never scores badly. A real UPI screenshot scores around 85 and comes out
"looks legit".

### What the member can see

Everything above, plus their own receipt image back — and nothing else. Their
receipt is visible to exactly two people: them and you. It lives in
`data/receipts/`, is never inside `public/static`, and the route that serves it
checks who is asking every time.

### Memberships tab

Admin → **Memberships** lists every membership with its dates, status and card
number.

- **Revoke** — ends it immediately, with a reason you type. The card stops working.
- **Reinstate** — brings it back and re-validates the card.
- **Run expiry sweep now** — forces the automatic check.

The sweep also runs by itself every time you open the admin panel or a member opens
My account, so expiry needs no button.

### About the code and SMS — the honest position

**Right now the code appears on screen**, in a box under the form, and a copy is
logged. Nobody should mistake that for security: it proves the person typing is the
person holding the receipt, which is what it is for, but it does *not* prove they
own the phone number.

To send real SMS, put a provider and key in `.env` (instructions are in
`.env.example`). **For Indian numbers you must also complete DLT registration with
your provider first** — TRAI requires the business, the sender ID and the message
template to be registered, and providers reject unregistered traffic. That
paperwork is against your business and takes a few days. Until it is done, the
on-screen code is what you have.

Once `FALCON_SMS_PROVIDER` and `FALCON_SMS_KEY` are set, the same code path posts a
real SMS and the on-screen copy disappears. Nothing else changes.

### Members re-signing in

Self-registered members are created with the standard
`member_FF_<firstname>` password unless they change it. They are flagged to change
it, and changing it now requires a one-time code — by design, so that a stolen
password alone cannot lock the real owner out of their own account.

### If you want lapsed members blocked at the door

By default a lapsed member can still sign in and see their history and the rate
card; they simply get no card and no active membership. If you would rather block
them entirely, set:

```
FALCON_REQUIRE_LIVE_MEMBERSHIP=1
```
