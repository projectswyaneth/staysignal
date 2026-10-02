# StaySignal — the business case, stress-tested

Measured on the held-out test set: **1000 customers**, 185 of whom
actually left (18.5%). Revenue counted 6 months ahead.
Nothing below is an estimate — it is the deployed model's own output, re-costed.

## 1. The three strategies at our stated assumptions

Offer costs 15% of the customer's revenue, we keep 35% of the leavers
we contact.

| Strategy | Revenue lost | vs doing nothing |
|---|---|---|
| Contact nobody | Rs. 1,614,006 | — |
| Contact everybody | Rs. 2,324,699 | Rs. -710,693 |
| **Contact who the model flags** | **Rs. 1,517,559** | **+ Rs. 96,447** |

We send 144 offers instead of 1000. 51 of those
144 go to people who were not leaving — that is the price of a
65%-precise model, and it is already inside
the number above.

## 2. Unit economics

| Measure | Value |
|---|---|
| Revenue protected per customer, 6 months | Rs. 96.45 |
| Revenue protected per customer per month | Rs. 16.07 |
| Offers sent per 1,000 customers | 144 |

Multiply the per-customer figure by the real prepaid base to size the case.
Do not quote a total we have not been given the base for.

## 3. Break-even: how wrong can we be?

**Save rate.** Our assumption is 35%. Targeting still beats doing nothing as
long as we keep at least **23.4%** of the leavers we contact.
Below that, the offers cost more than the customers are worth.

| Save rate | Nobody | Everybody | Targeted | Targeted vs nobody |
|---|---|---|---|---|
| 5% | Rs. 1,614,006 | Rs. 2,808,900 | Rs. 1,765,614 | Rs. -151,608 |
| 10% | Rs. 1,614,006 | Rs. 2,728,200 | Rs. 1,724,271 | Rs. -110,265 |
| 15% | Rs. 1,614,006 | Rs. 2,647,500 | Rs. 1,682,929 | Rs. -68,923 |
| 20% | Rs. 1,614,006 | Rs. 2,566,800 | Rs. 1,641,586 | Rs. -27,580 |
| 25% | Rs. 1,614,006 | Rs. 2,486,099 | Rs. 1,600,244 | +Rs. 13,762 |
| 30% | Rs. 1,614,006 | Rs. 2,405,399 | Rs. 1,558,902 | +Rs. 55,104 |
| 35% | Rs. 1,614,006 | Rs. 2,324,699 | Rs. 1,517,559 | +Rs. 96,447 |
| 40% | Rs. 1,614,006 | Rs. 2,243,998 | Rs. 1,476,217 | +Rs. 137,789 |
| 45% | Rs. 1,614,006 | Rs. 2,163,298 | Rs. 1,434,874 | +Rs. 179,132 |
| 50% | Rs. 1,614,006 | Rs. 2,082,598 | Rs. 1,393,532 | +Rs. 220,474 |
| 55% | Rs. 1,614,006 | Rs. 2,001,897 | Rs. 1,352,190 | +Rs. 261,816 |
| 60% | Rs. 1,614,006 | Rs. 1,921,197 | Rs. 1,310,847 | +Rs. 303,159 |
| 65% | Rs. 1,614,006 | Rs. 1,840,497 | Rs. 1,269,505 | +Rs. 344,501 |
| 70% | Rs. 1,614,006 | Rs. 1,759,797 | Rs. 1,228,162 | +Rs. 385,844 |

**Offer cost.** Our assumption is that an offer gives up 15% of the customer's
revenue. Targeting stops paying once an offer costs more than
**22.5%** of that revenue.

| Offer cost | Nobody | Targeted | Targeted vs nobody |
|---|---|---|---|
| 5% | Rs. 1,614,006 | Rs. 1,389,406 | +Rs. 224,600 |
| 10% | Rs. 1,614,006 | Rs. 1,453,483 | +Rs. 160,523 |
| 15% | Rs. 1,614,006 | Rs. 1,517,559 | +Rs. 96,447 |
| 20% | Rs. 1,614,006 | Rs. 1,581,636 | +Rs. 32,370 |
| 25% | Rs. 1,614,006 | Rs. 1,645,713 | Rs. -31,707 |
| 30% | Rs. 1,614,006 | Rs. 1,709,789 | Rs. -95,783 |
| 35% | Rs. 1,614,006 | Rs. 1,773,866 | Rs. -159,860 |
| 40% | Rs. 1,614,006 | Rs. 1,837,943 | Rs. -223,937 |
| 45% | Rs. 1,614,006 | Rs. 1,902,020 | Rs. -288,014 |
| 50% | Rs. 1,614,006 | Rs. 1,966,096 | Rs. -352,090 |

## 4. What this means commercially

- The case does not depend on the model being excellent. It depends on the
  offer being cheaper than the customer, and on not sending it to everyone.
- The two assumptions that carry the case are the save rate and the offer
  cost. Both are measurable in a four-week A/B test. Neither requires new
  technology to find out.
- Contacting everybody is worse than doing nothing at every save rate in the
  table above. That is the finding worth defending.
