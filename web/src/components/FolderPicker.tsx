import { useState, useEffect } from 'react'
import { Modal, Tree, Spin, Empty } from 'antd'
import { FolderOutlined, FolderOpenOutlined } from '@ant-design/icons'
import type { TreeDataNode } from 'antd'
import { getDirectoryTree } from '../api/files'

interface Props {
  open: boolean
  onOk: (folderId: number | null) => void
  onCancel: () => void
  title?: string
}

export default function FolderPicker({ open, onOk, onCancel, title = '选择目标文件夹' }: Props) {
  const [treeData, setTreeData] = useState<TreeDataNode[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)

  useEffect(() => {
    if (open) {
      setLoading(true)
      getDirectoryTree().then((res: any) => {
        const nodes = res.data || []
        const toTreeNode = (node: any): TreeDataNode => ({
          key: node.id,
          title: node.name,
          icon: <FolderOutlined />,
          children: node.children?.map(toTreeNode) || [],
        })
        setTreeData([{ key: 'root', title: '根目录', icon: <FolderOutlined />, children: nodes.map(toTreeNode) }])
      }).finally(() => setLoading(false))
    }
  }, [open])

  return (
    <Modal
      open={open}
      title={title}
      onOk={() => onOk(selected === null ? selected : selected)}
      onCancel={onCancel}
      okText="移动到此处"
      cancelText="取消"
      destroyOnClose
    >
      {loading ? <Spin style={{ display: 'block', padding: 24 }} /> :
        treeData.length === 0 ? <Empty description="暂无文件夹" /> :
        <Tree
          showIcon
          defaultExpandedKeys={['root']}
          selectedKeys={selected !== null ? [selected] : ['root']}
          onSelect={(keys) => {
            const key = keys[0]
            setSelected(key === 'root' ? null : Number(key))
          }}
          treeData={treeData}
          style={{ maxHeight: 400, overflow: 'auto' }}
        />
      }
    </Modal>
  )
}
