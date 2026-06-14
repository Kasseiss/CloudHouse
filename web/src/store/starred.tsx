import React, { createContext, useContext, useState, useCallback, useEffect } from 'react'

interface StarredContextType {
  starred: Set<number>
  toggle: (id: number) => void
  isStarred: (id: number) => boolean
}

const StarredContext = createContext<StarredContextType>({
  starred: new Set(), toggle: () => {}, isStarred: () => false,
})

export const useStarred = () => useContext(StarredContext)

export function StarredProvider({ children }: { children: React.ReactNode }) {
  const [starred, setStarred] = useState<Set<number>>(() => {
    try {
      const saved = localStorage.getItem('starred_files')
      return new Set(saved ? JSON.parse(saved) : [])
    } catch { return new Set() }
  })

  useEffect(() => {
    localStorage.setItem('starred_files', JSON.stringify([...starred]))
  }, [starred])

  const toggle = useCallback((id: number) => {
    setStarred(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const isStarred = useCallback((id: number) => starred.has(id), [starred])

  return (
    <StarredContext.Provider value={{ starred, toggle, isStarred }}>
      {children}
    </StarredContext.Provider>
  )
}
