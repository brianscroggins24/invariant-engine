# Engine glossary

**leg** — One part of a multi-part trade or scenario, tied to a particular market outcome. *Example (queue test)* — Leg B is the intended buy of 5 units of its outcome. Leg A is the other part of the scenario.

**order** — An instruction to buy or sell a specified quantity under stated terms. Submitting an order sends that instruction to a venue. *Example (queue test)* — The modeled order is to buy 5 units on B at 0.45 USD per unit. Nothing is sent to a venue.

**fill** — The part of an order that actually trades, or that a simulation records as traded. A fill can be partial. *Example (queue test)* — B fills 3 units of the intended 5 units, leaving 2 units open.

**cancellation** — Closing the unfilled part of an order without undoing earlier fills. A request alone leaves the remainder eligible to fill until cancellation completes. *Example (queue test)* — When B's cancellation completes, its remaining 2 units close unfilled and its 3 filled units stay acquired.

**exposure** — What you stand to lose on a position as the outcome changes, especially if another leg meant to offset it never fills. The accepted historical check measures payoff and profit or loss when all but one leg fill. *Example (queue test)* — B acquires 3 units while A is rejected, leaving the position dependent on B's outcome.

**edge** — For a hypothetical full purchase of all required legs, gross edge is payout minus purchase cost. Net edge also subtracts fees and is reported as a range when only fee bounds are known. *Example (model assumptions)* — Buying 5 units on each leg would pay 5.00 USD and cost 4.50 USD before fees. With 0.10 USD in assumed fees, gross edge is 0.50 USD and net edge is 0.40 USD.

**fixture** — Fixed test input that lets you repeat a case without relying on a live service. It can be a file or an in-memory value. *Example (queue test)* — The test keeps B's 5-unit buy and its cancellation request in a reusable in-memory scenario.

**authorization** — Explicit permission to proceed. A passing test checks expected behavior and grants no trading permission. Under **proposed Milestone 7 (inactive)**, an independent risk gateway would check whether a trade can proceed. Even a passing risk check would not send an order because submission is a separate execution step. *Example* — The test can pass for B's buy without sending anything to a venue.
