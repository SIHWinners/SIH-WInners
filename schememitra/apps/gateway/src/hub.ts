import type { WebSocket } from 'ws';

import type { Principal } from './auth.js';

export interface HubEvent {
  channel: string;
  event: string;
  data: unknown;
}

/**
 * In-memory pub/sub for status pushes. Channels:
 *   track:<tracking_id>   — anyone holding the tracking ID (it is the citizen's receipt)
 *   partner:<partner_id>  — officers of that partner
 *   admin                 — admins (SMS console, demo controls)
 * With several gateway replicas this would sit on Redis pub/sub; one replica is enough for a district pilot.
 */
export class Hub {
  private subs = new Map<string, Set<WebSocket>>();

  canSubscribe(channel: string, principal: Principal | null): boolean {
    if (channel.startsWith('track:')) return true;
    if (!principal) return false;
    if (principal.role === 'admin') return true;
    if (channel.startsWith('partner:')) {
      return principal.role === 'partner_officer' && channel === `partner:${principal.partnerId}`;
    }
    if (channel.startsWith('user:')) return channel === `user:${principal.userId}`;
    return false;
  }

  subscribe(channel: string, socket: WebSocket): void {
    let set = this.subs.get(channel);
    if (!set) {
      set = new Set();
      this.subs.set(channel, set);
    }
    set.add(socket);
    socket.once('close', () => this.unsubscribe(channel, socket));
  }

  unsubscribe(channel: string, socket: WebSocket): void {
    const set = this.subs.get(channel);
    set?.delete(socket);
    if (set && set.size === 0) this.subs.delete(channel);
  }

  publish(evt: HubEvent): number {
    const set = this.subs.get(evt.channel);
    if (!set) return 0;
    const frame = JSON.stringify(evt);
    let delivered = 0;
    for (const socket of set) {
      if (socket.readyState === socket.OPEN) {
        socket.send(frame);
        delivered += 1;
      }
    }
    return delivered;
  }

  stats(): Record<string, number> {
    return Object.fromEntries([...this.subs].map(([k, v]) => [k, v.size]));
  }
}
