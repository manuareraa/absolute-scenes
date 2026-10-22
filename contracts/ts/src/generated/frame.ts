/* Generated from contracts/schemas/frame.schema.json by scripts/gen_contracts.sh. Do not edit. */

/**
 * One tracking frame. Pitch metres, origin at the centre spot, x along the long axis (home attacks +x in period 1), y across. 105 x 68 pitch.
 */
export interface Frame {
  /**
   * Match clock in ms since kick-off of period 1.
   */
  t: number;
  period: number;
  ball: Ball;
  /**
   * @maxItems 30
   */
  players: PlayerState[];
}
export interface Ball {
  x: number;
  y: number;
  /**
   * Height in metres.
   */
  z: number;
  /**
   * Speed in m/s.
   */
  v: number;
  /**
   * Player id in possession, if any.
   */
  owner?: string | null;
}
export interface PlayerState {
  id: string;
  team: "home" | "away" | "ref";
  x: number;
  y: number;
  /**
   * Speed in m/s.
   */
  v: number;
  /**
   * Direction of travel in degrees, 0 = +x, counter-clockwise.
   */
  heading: number;
  /**
   * Facing direction in degrees, if different from heading.
   */
  body_heading?: number;
}
