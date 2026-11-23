# Waiver Scanning with Google Gemini: Cost Summary

**Date:** 23 November 2026

**Purpose:** What it will cost to digitize our handwritten visitor waivers with AI, and what we need to decide.

**Currency:** US dollars, before tax. Prices are Google's published rates as of 23 November 2026.

---

## The bottom line

> **Reading 100,000 waiver pages will most likely cost about $60 to $70.**
> Even in a worst case it should stay under **$165**.

| Question | Answer |
| --- | --- |
| **Most likely cost, 100,000 pages** | **$62** (about $69 with room for retries) |
| **Realistic range** | $35 to $165 |
| **Cost per page** | Well under a tenth of a cent, about **1,600 pages per dollar** |
| **Cost of a test run first** | **Under $1** |
| **Suggested budget to approve** | **$100**, prepaid, with automatic top-ups off |

The money is small. **The main decision is about privacy, not price** (see [Decision 1](#decision-1-use-the-paid-plan-for-privacy-reasons)).

---

## How much, at a glance

### Cost for 100,000 pages, by how much writing is on the pages

```
Light pages     $35  ██████
Typical pages   $62  ███████████  ◄ most likely
Dense pages    $149  ███████████████████████████
Dense+retries  $164  ██████████████████████████████  ◄ planning ceiling
```

- **Light:** many blank or cover pages, short entries.
- **Typical:** like the 38-page sample we tested, about one waiver every two pages.
- **Dense:** every page is a full waiver with long notes.

### How the cost grows with volume (typical pages)

| Pages | Cost |
| ---: | ---: |
| 1,000 | $0.62 |
| 10,000 | $6.24 |
| **100,000** | **$62.41** |
| 1,000,000 | $624 |

Cost grows in a straight line. There are no volume penalties or price jumps for large jobs.

---

## Where the money goes

Google charges for what goes **in** (the scanned pages and our instructions) and what comes **out** (the typed-up results). Output is priced about eight times higher than input, so it is most of the bill.

```
Typical job, 100,000 pages = $62.41

Typed-up results       $25.00  ████████████████  40%
AI "thinking" time     $18.75  ████████████      30%
Scanned page images    $16.80  ███████████       27%
Our instructions        $1.86  █                  3%
```

**"Thinking"** is work the AI does before it answers. We pay for it but never see it. It is also **the one number we have not measured yet**, which is why the range is wide. A $1 test run would pin it down.

---

## Why we chose this AI model

We use Google's **Gemini 3.5 Flash-Lite**, which Google describes as built for low-cost document reading. It is the cheapest current model with no announced retirement date.

```
Typical cost for 100,000 pages

Gemini 3.5 Flash-Lite (ours)      $62   ████████
Gemini 3.1 Flash-Lite *           $42   ██████
Gemini 3.8 Flash, today          $112   ███████████████
Gemini 3.8 Flash, from Jan 2027  $225   ██████████████████████████████
Gemini 4 Hydrogen (newest)       $225   ██████████████████████████████

* Cheaper, but Google retires it in May 2027.
```

An earlier version of our app could quietly fall back to the more expensive Gemini 3.8 Flash by mistake. **That was fixed on 19 November.**

---

## What we need to decide

### Decision 1: Use the paid plan, for privacy reasons

Google offers a free plan, but its terms say:

> *"Do not submit sensitive, confidential, or personal information to the Unpaid Services."*

On the free plan, Google may use what we send to improve its products, and **its staff may read it**. Our waivers contain names, addresses, phone numbers, emergency contacts and health details.

| | Free plan | Paid plan |
| --- | --- | --- |
| Cost for 100,000 pages | $0 | About $62 |
| Google may use our data to improve its products | **Yes** | No |
| Google staff may read our data | **Yes** | No (kept briefly for abuse checks and legal requirements only) |
| Speed | Slow: strict daily limits | Faster: higher limits |

**Recommendation: use the paid plan.** About $62 is a small price for keeping customers' personal details out of Google's product training and away from human review.

*(Exception: if our Google account is registered in the EU, Switzerland or the UK, Google applies the paid-plan privacy terms even to free use. We still need to confirm which country our account is in.)*

### Decision 2: Approve a $100 prepaid budget

- We buy $100 of credit up front. **When it is used up, the service simply stops.** It cannot run over by more than a few cents.
- Automatic top-ups stay **off**.
- $100 covers the full 100,000 pages in the light and typical cases, with room to spare. Only the dense worst case ($164) would need one more top-up, and we would see that coming during the job.
- Unused credit expires after 12 months and is not refundable.

### Decision 3: Run a $1 test before the full job

We process 10 to 20 real waiver files first. The app already records exactly what each file costs, so this turns our estimate into a measured figure **before** we commit to the full job.

---

## Risks, and how we handle them

| Risk | How likely | What we do about it |
| --- | --- | --- |
| **Paying for the same work twice.** Changing the AI's instructions or switching models mid-project makes the app re-read every file. | Avoidable | Lock the instructions and model before the big run. |
| **Cost lands higher than $62.** "Thinking" time hasn't been measured. | Possible | The $1 test measures it. Even the worst case is about $165. |
| **Runaway spending** | Very low | Prepaid credit stops at $0. We also set a spending cap in Google's dashboard. |
| **Retries cost extra.** If the AI gives an unusable answer, the file is re-read and billed again. | Low | Already included: the 10% allowance in our estimate. |
| **Price changes.** | Low | Google lists no planned price change for our model. |

---

## How long it will take

The app reads one file at a time. If each file takes 30 to 60 seconds, 100,000 pages (about 2,600 files) takes roughly **one to two days of running time** on the paid plan. On the free plan, daily limits could stretch this out much further.

Google doesn't publish exact speeds, so we will get a real number from the test run.

---

## Ways to cut the cost further (optional)

These need engineering work and quality testing. None is necessary at this price.

```
Typical cost for 100,000 pages

Current setup                       $62  █████████████████████████
Less AI "thinking"                  $44  ██████████████████
Overnight batch mode                $31  ████████████
Both together                       $22  █████████
```

- **Overnight batch mode:** Google charges **half price** if we accept results within 24 hours instead of right away. This is the most reliable saving.
- **Less AI "thinking":** may lower cost, but could reduce accuracy on handwriting. Needs testing.

At this scale, the savings are about $30 to $40 in total. **We don't recommend spending engineering time on this unless the volume grows a lot.**

---

## Summary of recommendations

1. ✅ **Use the paid plan** to protect customers' personal data.
2. ✅ **Approve a $100 prepaid budget** with automatic top-ups off.
3. ✅ **Run a test of under $1** on 10 to 20 real files before the full job.
4. ✅ **Lock the setup** (model and instructions) before the full run, so we never pay twice.
5. ⏸️ **Skip cost-cutting work for now.** The potential savings are too small to justify it.

---

<sub>Figures come from Google's official pricing and documentation (checked 23 November 2026) and from a 38-page sample file. The "thinking" and output amounts are estimates until the test run. The full technical analysis is in GEMINI_OCR_COST_ANALYSIS.md.</sub>
