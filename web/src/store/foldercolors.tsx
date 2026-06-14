import React, { createContext, useContext, useState, useCallback, useEffect } from 'react'

const COLORS = ['#faad14', '#1677ff', '#52c41a', '#ff4d4f', '#722ed1', '#13c2c2', '#eb2f96', '#fa8c16']

interface FolderColorsContextType {
  colors: Record<number, string>
  setColor: (id: number, color: string) => void
  getColor: (id: number) => string | undefined
  COLORS: string[]
}

const FolderColorsContext = createContext<FolderColorsContextType>({
  colors: {}, setColor: () => {}, getColor: () => undefined, COLORS: [],
})

export const useFolderColors = () => useContext(FolderColorsContext)

export function FolderColorsProvider({ children }: { children: React.ReactNode }) {
  const [colors, setColors] = useState<Record<number, string>>(() => {
    try {
      return JSON.parse(localStorage.getItem('folder_colors') || '{}')
    } catch { return {} }
  })

  useEffect(() => {
    localStorage.setItem('folder_colors', JSON.stringify(colors))
  }, [colors])

  const setColor = useCallback((id: number, color: string) => {
    setColors(prev => ({ ...prev, [id]: color }))
  }, [])

  const getColor = useCallback((id: number) => colors[id], [colors])

  return (
    <FolderColorsContext.Provider value={{ colors, setColor, getColor, COLORS }}>
      {children}
    </FolderColorsContext.Provider>
  )
}
