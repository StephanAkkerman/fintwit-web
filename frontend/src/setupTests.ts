import '@testing-library/jest-dom'

// Components format with the viewer's locale (`toLocaleString(undefined, …)`),
// so assertions on "$1,250" only hold on an en-US machine. Pin the default
// locale so the suite gives the same result wherever it runs.
const TEST_LOCALE = 'en-US'

const withDefaultLocale = <A extends unknown[], R>(fn: (locale?: Intl.LocalesArgument, ...rest: A) => R) =>
  function (this: unknown, locale?: Intl.LocalesArgument, ...rest: A): R {
    return fn.call(this, locale ?? TEST_LOCALE, ...rest)
  }

for (const [proto, names] of [
  [Number.prototype, ['toLocaleString']],
  [Date.prototype, ['toLocaleString', 'toLocaleDateString', 'toLocaleTimeString']],
] as const) {
  for (const name of names) {
    const original = (proto as unknown as Record<string, never>)[name] as (...args: unknown[]) => unknown
    Object.defineProperty(proto, name, {
      configurable: true,
      writable: true,
      value: withDefaultLocale(original),
    })
  }
}

for (const name of ['NumberFormat', 'DateTimeFormat'] as const) {
  const Original = Intl[name] as unknown as new (locale?: Intl.LocalesArgument, options?: object) => object
  Intl[name] = new Proxy(Original, {
    construct: (target, [locale, options]) => new target(locale ?? TEST_LOCALE, options),
    apply: (target, _this, [locale, options]) => new target(locale ?? TEST_LOCALE, options),
  }) as never
}
