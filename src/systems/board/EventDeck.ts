/**
 * Flux Event deck: 16 original cards with typed, machine-applied
 * effects. The deck is a seeded shuffle of card indices stored in the
 * game state (deckOrder + deckIndex); when exhausted it reshuffles
 * deterministically from the same RNG cursor, so draws are fully
 * reproducible from a share code.
 */

export type CardEffect =
  | { type: 'money'; amount: number } // +gain / -cost
  | { type: 'moveTo'; pos: number; collectStart: boolean }
  | { type: 'moveBy'; delta: number }
  | { type: 'perLevel'; amount: number } // pay per upgrade level owned
  | { type: 'fromEach'; amount: number } // collect from each rival
  | { type: 'toEach'; amount: number } // pay each rival
  | { type: 'toNearestTransit' };

export interface CardDef {
  name: string;
  text: string;
  effect: CardEffect;
}

export const EVENT_CARDS: readonly CardDef[] = [
  { name: 'Grid Dividend', text: 'The power co-op pays out. Collect 50 cr.', effect: { type: 'money', amount: 50 } },
  { name: 'Festival Crowd', text: 'Lantern festival floods your blocks. Collect 100 cr.', effect: { type: 'money', amount: 100 } },
  { name: 'Neon Grant', text: 'City arts board funds your signage. Collect 150 cr.', effect: { type: 'money', amount: 150 } },
  { name: 'Data Refund', text: 'Bandwidth overcharge refunded. Collect 125 cr.', effect: { type: 'money', amount: 125 } },
  { name: 'Skim Fine', text: 'Caught skimming the grid. Pay 75 cr.', effect: { type: 'money', amount: -75 } },
  { name: 'Power Bill', text: 'Peak-hour surcharge. Pay 60 cr.', effect: { type: 'money', amount: -60 } },
  { name: 'Audit', text: 'The levy office finds discrepancies. Pay 100 cr.', effect: { type: 'money', amount: -100 } },
  { name: 'Spire Patches', text: 'Storm damage. Pay 40 cr per development level you own.', effect: { type: 'perLevel', amount: 40 } },
  { name: 'Crowdfund', text: 'Your district pitch goes viral. Collect 25 cr from each rival.', effect: { type: 'fromEach', amount: 25 } },
  { name: 'Street Repairs', text: 'Shared infrastructure bill. Pay 25 cr to each rival.', effect: { type: 'toEach', amount: 25 } },
  { name: 'Express Home', text: 'Advance to Plaza Gate and collect the stipend.', effect: { type: 'moveTo', pos: 0, collectStart: true } },
  { name: 'Night Market Run', text: 'Head to the Night Market corner.', effect: { type: 'moveTo', pos: 14, collectStart: true } },
  { name: 'Spire Invitation', text: 'Advance to Spire Heights.', effect: { type: 'moveTo', pos: 26, collectStart: true } },
  { name: 'Maintenance Recall', text: 'Your pawn is recalled to the Maintenance Bay.', effect: { type: 'moveTo', pos: 7, collectStart: false } },
  { name: 'Wrong Exit', text: 'Move back 3 spaces.', effect: { type: 'moveBy', delta: -3 } },
  { name: 'Skyrail Pass', text: 'Ride to the nearest Skyrail node.', effect: { type: 'toNearestTransit' } },
];
