import { useState, useEffect, useCallback } from 'react'
import { Tree, Spin } from 'antd'
import { FolderOutlined, FolderOpenOutlined } from '@ant-design/icons'
import type { TreeDataNode } from 'antd'
import { getDirectoryTree } from '../api/files'

interface DirNode {
  id: number
  name: string
  parent_id: number | null
  children: DirNode[]
}

interface Props {
  onSelect: (folderId: number | null) => void
  selectedId: number | null
  refreshKey?: number
  onDropFile?: (fileId: number, targetFolderId: number | null) => void
}

export default function DirectoryTree({ onSelect, selectedId, refreshKey, onDropFile }: Props) {
  const [treeData, setTreeData] = useState<TreeDataNode[]>([])
  const [loading, setLoading] = useState(false)

  const fetchTree = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await getDirectoryTree()
      const nodes = res.data || []

      const toTreeNode = (node: DirNode): TreeDataNode => ({
        key: node.id,
        title: node.name,
        icon: ({ selected }: any) => selected ? <FolderOpenOutlined /> : <FolderOutlined />,
        children: node.children?.map(toTreeNode) || [],
      })

      const rootNode: TreeDataNode = {
        key: 'root',
        title: '根目录',
        icon: <FolderOutlined />,
        children: nodes.map(toTreeNode),
      }

      setTreeData([rootNode])
    } catch {
      // handled
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchTree() }, [fetchTree, refreshKey])

  const handleSelect = (keys: any[]) => {
    if (keys.length === 0) return
    const key = keys[0]
    onSelect(key === 'root' ? null : Number(key))
  }

  if (loading) return <Spin style={{ padding: 24 }} />
  if (treeData.length === 0) return null

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const fileId = parseInt(e.dataTransfer.getData('text/plain'))
    if (!fileId || !onDropFile) return

    // 查找 drop 位置下方最近的文件夹节点
    const target = (e.target as HTMLElement).closest('.ant-tree-node-content-wrapper') as HTMLElement
    if (target) {
      const titleEl = target.querySelector('.ant-tree-title')
      // 通过 key 找到节点 id
      const nodeEl = target.closest('.ant-tree-treenode') as HTMLElement
      if (nodeEl) {
        const key = nodeEl.getAttribute('data-key') || nodeEl.querySelector('[data-key]')?.getAttribute('data-key')
        // For "root" key, target is null (root directory)
        // For other keys, parse the numeric ID
        const targetId = key && key !== 'root' ? parseInt(key) : null
        onDropFile(fileId, targetId)
      }
    }
  }

  return (
    <div onDragOver={handleDragOver} onDrop={handleDrop}>
      <Tree
        showIcon
        defaultExpandedKeys={['root']}
        selectedKeys={[selectedId ?? 'root']}
        onSelect={handleSelect}
        treeData={treeData}
        style={{ padding: '8px 0' }}
      />
    </div>
  )
}
