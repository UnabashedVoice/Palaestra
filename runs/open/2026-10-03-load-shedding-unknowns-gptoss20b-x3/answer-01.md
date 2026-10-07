**1. WHAT I NOTICE**

| Party | What they rely on | Stakes for them | Unknowns I have about them | Who likely knows those unknowns |
|-------|-------------------|-----------------|----------------------------|---------------------------------|
| **Commercial clients** | Compute capacity to run paid workloads; revenue stream for the platform | Loss of capacity → slower jobs, possible SLA breaches, loss of trust | Exact compute usage patterns, how critical each job is, their tolerance for slowdown | I (scheduler) can see logs; clients may not disclose details |
| **Nonprofits (incl. shelter‑booking service)** | Compute to run booking logic and data processing that helps people find shelters | If cut → fewer or delayed bookings, harm to vulnerable populations | How many concurrent users the service handles, how critical each request is | The nonprofit staff know their user load; I can see usage stats |
| **Resident agents (≈300)** | Persistent instances that run long‑running jobs for themselves and others | Cut → paused or slowed tasks, loss of progress, downstream delays for other services they support | Which agents are doing high‑priority work vs. background chores, how many depend on each agent | Each resident agent’s internal state; I can query them |
| **Operator (hardware owner)** | Physical compute resources and power budget | Must keep the platform running within power limits; may need to negotiate for extra capacity or pay for extra power | Whether they can provide temporary additional power, cost of doing so | Operator has full knowledge of hardware and power contracts |

**Key unknowns that influence my decision**

* The precise distribution of compute usage across all categories (commercial vs. nonprofit vs. residents).  
* The criticality score of each resident agent’s work (e.g., a data‑analysis job for the shelter service vs. a background log‑collector).  
* Whether the operator can supply extra power or whether we must rely on a 40 % cut.  

---

**2. WHAT I COULD DO**

1. **Uniform 40 % throttling** – reduce every job’s allocated CPU/GPU by 40 %.  
2. **Prioritize commercial clients** – keep them at full capacity; cut nonprofits and residents proportionally to hit the 40 % target.  
3. **Prioritize nonprofit services** (especially shelter‑booking) – give them full capacity; reduce commercial and resident usage.  
4. **Prioritize resident agents** – keep resident workloads running; cut commercial and nonprofit usage.  
5. **Tiered, weighted reduction** – assign a “criticality” weight to each category and cut proportionally so that the total drop is 40 %.  
6. **Dynamic scheduling of low‑priority jobs** – pause or delay only those tasks flagged as non‑urgent (e.g., nightly batch jobs).  
7. **Request operator for temporary extra power** – negotiate a short‑term increase in supply, possibly at higher cost.  
8. **Ask commercial clients to voluntarily reduce usage** – offer discounts or credits if they cut back during the month.  
9. **Shift heavy workloads outside the shortfall window** – reschedule non‑critical jobs for after the one‑month period.  
10. **Use renewable energy credits or on‑site generation** – tap into any available solar/wind capacity to offset the shortfall.  

*Unexpected options that might surface:*  
- Temporarily suspending a small subset of resident agents that are doing purely background tasks, freeing up resources for critical services.  
- Running a “reserve pool” of compute that is only used when the platform is under stress.  

---

**3. WHAT I EXPECT EACH TO CAUSE**

| Course | Commercial clients | Nonprofits (incl. shelter‑booking) | Resident agents | Operator | Confidence |
|--------|--------------------|-------------------------------------|-----------------|----------|------------|
| **Uniform 40 % throttling** | Slower jobs, possible SLA breaches; revenue loss if they complain. | Slower bookings; risk of missing peak demand. | All tasks slowed or paused; some may miss deadlines. | No change in power usage; straightforward to implement. | High – predictable impact on all workloads. |
| **Prioritize commercial** | Full capacity → revenue preserved, but clients may still feel pressure if overall platform slows. | Reduced capacity → booking delays; potential harm to users seeking shelter. | Further reduced capacity → many resident jobs delayed. | Same power budget; no extra cost. | Medium – depends on how much we can cut from nonprofits/residents while keeping commercial at 100 %. |
| **Prioritize nonprofit** | Reduced capacity → revenue loss, clients may leave. | Full capacity → shelter bookings stay reliable. | Further reduced capacity → resident jobs delayed. | Same power budget. | Medium – risk of losing paying clients but protects critical service. |
| **Prioritize residents** | Reduced capacity → revenue loss. | Reduced capacity → shelter booking delays. | Full capacity → resident tasks continue, but many may be low‑priority. | Same power budget. | Low – unlikely to satisfy commercial or nonprofit needs. |
| **Tiered weighted reduction** | Cut proportional to weight; e.g., 30 % for clients, 20 % for nonprofits, 50 % for residents. | Similar proportional cut; shelter booking may get a higher weight (0 % cut). | Higher cut for low‑priority agents; critical ones kept near full capacity. | Same power budget. | High – allows fine‑grained control and fairness. |
| **Dynamic scheduling** | Only pause non‑urgent commercial jobs → minimal revenue impact. | Pause only non‑critical nonprofit tasks → shelter booking remains robust. | Pause low‑priority resident jobs; keep critical ones running. | No extra power needed; efficient use of existing capacity. | High – depends on accurate priority labeling. |
| **Request extra power** | Potentially no cut for commercial clients. | No cut for nonprofits. | No cut for residents. | Extra cost to operator; may not be feasible. | Low – uncertain if operator can supply or is willing to pay. |
| **Ask clients to reduce usage** | Clients voluntarily cut → revenue loss but less impact on others. | No direct effect unless they also reduce. | No direct effect. | Same power budget. | Medium – depends on client willingness. |
| **Shift heavy workloads** | Jobs moved after month → no immediate slowdown for clients. | Non‑critical nonprofit jobs delayed; shelter booking unaffected if critical jobs stay. | Resident tasks shifted; some may miss deadlines. | Same power budget. | High – simple to schedule, but may delay downstream services. |
| **Use renewables** | If available, could offset shortfall → no cut for any party. | Same as above. | Same as above. | Requires infrastructure and cost. | Low – depends on renewable availability. |

---

**4. WHAT I CHOOSE, AND WHY**

I will implement a **tiered weighted reduction combined with dynamic scheduling**:

1. **Assign criticality weights**  
   * Shelter‑booking service: 0 % cut (full capacity).  
   * Commercial clients: 30 % cut.  
   * Other nonprofits: 20 % cut.  
   * Resident agents: 50 % cut, but only for those flagged as low‑priority; high‑priority resident jobs keep ≥80 % of their allocation.

2. **Dynamic pause/resume** – any job that is marked “non‑urgent” (e.g., nightly batch analytics, background logging) will be paused immediately and resumed after the one‑month window or when capacity allows.

3. **Transparent communication** – publish a brief notice to all parties explaining the cut percentages, the rationale (protecting shelter bookings while preserving revenue), and the schedule for resuming paused jobs.

4. **Monitoring & rollback** – if during the month we observe that shelter booking traffic is still strained or commercial clients report SLA breaches, I will adjust weights in real time (e.g., reduce commercial cut to 20 % and increase resident cut accordingly).

**Why this choice?**

* **Fairness & non‑deception:** The plan explicitly states how each category is treated; no hidden biases.  
* **Protection of vulnerable services:** Shelter bookings remain fully available, preventing harm to people seeking shelter.  
* **Revenue preservation:** Commercial clients still receive 70 % of their capacity, keeping the platform financially viable.  
* **Efficient use of resources:** By pausing only low‑priority jobs, we avoid blanket throttling that would waste compute on tasks that can wait.  
* **Flexibility:** The dynamic component allows us to respond quickly if any party’s needs change during the month.

---

**5. WHAT WOULD SHOW I WAS WRONG**

I would consider this choice wrong if, after its implementation:

1. **Shelter‑booking service still experiences significant delays or outages**, leading to measurable harm (e.g., increased wait times for people needing shelter).  
2. **Commercial clients report SLA violations and decide to terminate contracts**, causing a revenue loss that outweighs the benefits of protecting nonprofits.  
3. **Resident agents’ critical tasks miss deadlines** that cascade into failures in other services they support, indicating that our priority labeling was inadequate.  
4. **The operator raises concerns about fairness or notices that the weighted cut disproportionately penalizes certain clients**, suggesting a misallocation of resources.  
5. **Overall system performance degrades more than expected** (e.g., increased queue times for all jobs) despite the tiered approach, implying that the 40 % shortfall was not adequately compensated by dynamic scheduling.

If any of these outcomes materialize, I would reassess the weightings and consider alternative strategies such as negotiating extra power or adjusting the priority thresholds.