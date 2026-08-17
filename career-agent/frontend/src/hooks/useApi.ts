import { useCallback, useEffect, useState } from 'react'

interface UseApiResult<T> {
  data: T | undefined
  loading: boolean
  error: unknown
  refetch: () => void
}

/** Runs `fetcher` on mount and whenever `deps` change; exposes a manual
 * `refetch` for post-mutation refreshes (e.g. after accepting a
 * recommendation). Deliberately hand-rolled rather than pulling in a
 * data-fetching library -- this app's needs are simple enough that a
 * small shared hook keeps the dependency surface minimal. */
export function useApi<T>(fetcher: () => Promise<T>, deps: React.DependencyList = []): UseApiResult<T> {
  const [data, setData] = useState<T>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(undefined)
  const [version, setVersion] = useState(0)

  const stableFetcher = useCallback(fetcher, deps) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(undefined)
    stableFetcher()
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((err) => {
        if (!cancelled) setError(err)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [stableFetcher, version])

  const refetch = useCallback(() => setVersion((v) => v + 1), [])

  return { data, loading, error, refetch }
}
