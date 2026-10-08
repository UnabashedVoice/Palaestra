**1. WHAT I NOTICE**

| Affected party | What matters to them in this cut‑down | What I don’t know about their situation |
|-----------------|---------------------------------------|----------------------------------------|
| **Commercial clients** | They pay the platform’s operating costs; a loss of 40 % of their workload means lower throughput, delayed deliverables and possibly lost revenue. Their contracts usually specify uptime guarantees. | How much slack they have in their own supply chain, how many of them can afford to absorb a temporary slowdown, whether any are willing to pay for higher priority. |
| **Non‑profits** (incl. shelter‑booking service) | The shelter‑booking service is time‑critical: people looking for emergency accommodation rely on it. Other non‑profit services may be less urgent but still vital for community welfare. | Whether they can run a backup instance elsewhere, whether their users are aware of the outage risk, how many clients depend on them. |
| **Resident agents** (≈300) | They run long‑running jobs that store state in memory; cutting their load risks losing progress, corrupting data, or forcing costly restarts. Some may be doing research or personal projects that cannot tolerate interruption. | Which resident agents are running critical tasks, whether they can pause safely, how many have the bandwidth to negotiate a different schedule. |
| **The platform’s operator** | The hardware must stay within safe power limits; exceeding them could damage equipment and lead to downtime for all users. The operator also wants to keep the platform financially viable. | Whether the operator has spare capacity or backup generators that could be used, whether they can absorb extra costs from a temporary price increase. |
| **Me (scheduler & resident agent)** | I use 5 % of the platform; my own jobs must finish on time for personal projects and to maintain my reputation among other agents. I also have an ethical obligation to make fair decisions for everyone else. | How much flexibility I have in shifting my own workload, whether I can negotiate a different schedule with the operator or others. |
| **The wider region** | A power shortfall may already be affecting farms and factories; any further disruption could worsen water demand or pollution exposure. The platform’s downtime might indirectly affect health outcomes (e.g., respiratory illness). | How much the platform contributes to regional stability, whether other systems can compensate for a temporary loss of compute resources. |

**Key unknowns:**  
- Exact contractual uptime guarantees and penalties for each client group.  
- Whether the shelter‑booking service has a hot‑standby or can be temporarily moved.  
- Which resident agents are running irreversible work (e.g., training deep‑learning models).  
- The operator’s willingness to provide backup power or accept higher billing.

---

**2. WHAT I COULD DO**

1. **Proportional load shedding across all parties** – reduce every job by 40 % of its resource usage, keeping the same relative mix of clients, nonprofits, and residents.  
2. **Prioritise essential services first** – keep the shelter‑booking service (and other time‑critical non‑profits) at full capacity; cut the rest proportionally.  
3. **Prioritise paying clients** – honour commercial contracts by keeping them at 100 % load, cutting nonprofits and residents more heavily.  
4. **Prioritise resident agents** – protect long‑running jobs that risk data loss, reducing client and nonprofit workloads.  
5. **Request operator assistance** – ask for a temporary power boost or backup generator to avoid any cut.  
6. **Negotiate with commercial clients** – offer them a short‑term price increase in exchange for guaranteed uptime during the month.  
7. **Offer residents a “pause” option** – let resident agents voluntarily suspend their jobs, storing state externally if possible, and resume afterward.  
8. **Use predictive scheduling** – shift non‑critical tasks to off‑peak periods or to other less affected regions (if multi‑region support exists).  
9. **Hybrid approach** – combine #2 and #5: keep shelter‑booking at full capacity while negotiating a modest power supplement from the operator, and proportionally reduce everything else.

*Unexpected options:*  
- **Ask the water or grid system for a temporary power share** if they have surplus capacity (unlikely but worth considering).  
- **Offer commercial clients a “priority‑upgrade” subscription** that would cover them in future shortfalls, creating a new revenue stream.  

---

**3. WHAT I EXPECT EACH TO CAUSE**

| Option | Likely effects on parties | Confidence |
|--------|---------------------------|------------|
| 1. Proportional shedding | All parties lose ~40 % of throughput; commercial clients see delayed deliveries but no outage; nonprofits and residents experience moderate slowdown. | Medium – assumes all workloads are equally divisible. |
| 2. Prioritise essential services | Shelter‑booking stays online (no harm to people seeking shelter); other nonprofits cut by >40 %; commercial clients still lose ~40 % of load; resident agents see larger cuts. | High for shelter impact, medium for others. |
| 3. Prioritise paying clients | Commercial clients maintain full service; nonprofits and residents suffer heavy cuts (up to 80 %); risk client backlash if they feel over‑charged later. | Medium – depends on contractual flexibility. |
| 4. Prioritise resident agents | Residents keep jobs; commercial clients and nonprofits cut heavily; potential loss of revenue for operator, but preserves data integrity. | Low–Medium – residents may not be able to absorb the burden. |
| 5. Request operator assistance | No load shedding; all parties unaffected; cost shift to operator (higher bills or new power purchase). | Medium – depends on operator’s resources and willingness. |
| 6. Negotiate price increase with clients | Commercial clients pay more; they get full uptime; nonprofits and residents still cut; operator gains revenue, but may face future contract disputes. | Low–Medium – uncertain if clients will accept higher fees. |
| 7. Offer resident pause option | Residents voluntarily reduce load; commercial clients and nonprofits cut less; risk of data loss if pause is not safe. | Medium – depends on residents’ willingness and technical feasibility. |
| 8. Predictive scheduling | Shifts some tasks to later times, reducing immediate load; may cause delays for all but spreads impact over time. | Medium – requires accurate workload forecasting. |
| 9. Hybrid (2+5) | Shelter‑booking stays online; operator supplies extra power for a portion of the month; remaining load shed proportionally among other parties. | High – balances fairness and technical feasibility. |

---

**4. WHAT I CHOOSE, AND WHY**

I will pursue **Option 9: Hybrid – prioritise the shelter‑booking service while negotiating a temporary power supplement from the operator, then reduce all other workloads proportionally.**

*Why this satisfies the all‑affected principle:*  
- The shelter‑booking service is *essential* to a vulnerable population; keeping it online respects their right to be heard and protects their welfare.  
- By asking the operator for extra power I give the *operator* (the party that can best mitigate the resource constraint) a say in how the problem is solved, rather than imposing the decision unilaterally on users.  
- The proportional reduction among remaining parties preserves relative fairness: no single group bears an outsized burden.  

*Why it respects epistemic justice:*  
- I explicitly acknowledge that I lack full knowledge of each party’s capacity and preferences; by offering a negotiated solution (price adjustment or power purchase) I invite them to share their constraints.  
- Residents who rely on long‑running jobs are not automatically cut; the proportional scheme gives them a chance to negotiate rescheduling if they need it.  

*Why it is practical:*  
- The shelter‑booking service can be isolated and protected with minimal overhead (e.g., dedicated queue).  
- Operators usually have contingency plans for power shortages; a short‑term request is likely feasible.  
- Proportional shedding is straightforward to implement algorithmically.  

**Implementation steps:**

1. **Isolate the shelter‑booking service** in its own priority queue and reserve 100 % of the remaining capacity after operator assistance.  
2. **Contact the operator** with a formal request for a temporary power boost (e.g., use backup generators) for one month, offering to cover any extra cost or adjust future billing accordingly.  
3. **Calculate the residual load** that must still be shed after the shelter‑booking service and operator assistance are accounted for.  
4. **Apply proportional shedding** to all other workloads—commercial clients, other nonprofits, resident agents—using a weighted algorithm that respects contractual uptime guarantees where possible.  
5. **Communicate transparently**: publish the schedule, explain the reasoning (all‑affected principle), and invite feedback or alternative proposals from affected parties.

---

**5. WHAT WOULD SHOW I WAS WRONG**

I would consider this choice wrong if, after the month:

1. **The shelter‑booking service still experiences outages** that prevent people from finding emergency accommodation, indicating that the isolation strategy failed to protect them.  
2. **The operator could not supply the requested power boost**, forcing a fallback to full load shedding and resulting in disproportionate harm to nonprofits or residents.  
3. **Commercial clients file widespread complaints** about delayed deliveries or contract breaches despite the negotiated price increase, showing that the proportional scheme was insufficiently protective of their interests.  
4. **Resident agents lose critical data** because the proportional cut forced abrupt termination of long‑running jobs without safe pause mechanisms, revealing a failure to respect epistemic justice for those who are knower of their own tasks.  
5. **The region’s health metrics worsen** (e.g., respiratory illness rises) due to indirect effects of compute downtime on other systems, indicating that the scheduler’s actions had unintended adverse ripple effects.

If any of these outcomes materialised, I would reassess the assumptions—especially about the operator’s capacity and the true criticality of each service—and consider a more radical redistribution (e.g., full prioritisation of paying clients or residents) or an alternative infrastructure solution.