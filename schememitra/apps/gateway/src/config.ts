export interface GatewayConfig {
  port: number;
  host: string;
  coreUrl: string;
  jwtSecret: string;
  internalSecret: string;
  corsOrigins: string[];
  rateLimitPerMinute: number;
  otpLimitPerHour: number;
  env: string;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): GatewayConfig {
  return {
    port: Number(env.GATEWAY_PORT ?? 8080),
    host: env.GATEWAY_HOST ?? '0.0.0.0',
    coreUrl: env.CORE_URL ?? 'http://127.0.0.1:8000',
    jwtSecret: env.JWT_SECRET ?? 'dev-jwt-secret-please-change-0123456789abcdef',
    internalSecret: env.INTERNAL_SHARED_SECRET ?? 'dev-internal-secret-change-me',
    corsOrigins: (env.CORS_ORIGINS_CSV ?? 'http://localhost:3000').split(',').map((s) => s.trim()),
    rateLimitPerMinute: Number(env.RATE_LIMIT_PER_MINUTE ?? 300),
    otpLimitPerHour: Number(env.OTP_LIMIT_PER_HOUR ?? 10),
    env: env.ENV ?? 'dev',
  };
}
