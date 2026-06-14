import { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Table, Button, Space, Breadcrumb, Upload, Modal, Input, Alert,
  Dropdown, message, Tag, Tooltip, Progress, Empty, Card, Row, Col, Layout, Segmented,
} from 'antd'
import type { UploadProps } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  FolderOutlined, FolderOpenOutlined, FileOutlined, UploadOutlined, FolderAddOutlined,
  DeleteOutlined, EditOutlined, DownloadOutlined, ShareAltOutlined,
  SearchOutlined, ReloadOutlined, AppstoreOutlined, UnorderedListOutlined,
  CopyOutlined, EyeOutlined, KeyOutlined, StarOutlined, StarFilled, LinkOutlined,
} from '@ant-design/icons'
import {
  getFileList, uploadFiles, uploadFileWithChunks, mkdir, touchFile, renameFile, moveFiles, copyFile,
  deleteFile, getDownloadUrl, getPreviewUrl, searchFiles, getBreadcrumb, batchDownload, getRecentFiles, importFromUrl, batchRename,
} from '../api/files'
import { useAuth } from '../store/auth'
import { useStarred } from '../store/starred'
import { createShare } from '../api/shares'
import { changePassword } from '../api/auth'
import type { MenuProps } from 'antd'
import DirectoryTree from '../components/DirectoryTree'
import PreviewModal from '../components/PreviewModal'
import FolderPicker from '../components/FolderPicker'
import FileDetail from '../components/FileDetail'
import RecentActivity from '../components/RecentActivity'

const { Sider, Content: LayoutContent } = Layout
import dayjs from 'dayjs'

interface FileItem {
  id: number
  name: string
  file_size: number
  mime_type: string
  is_dir: boolean
  parent_id: number | null
  created_at: string
  updated_at: string
}

const formatBytes = (bytes: number) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB'
  return (bytes / 1073741824).toFixed(2) + ' GB'
}

export default function HomePage() {
  const { user } = useAuth()
  const { isStarred, toggle: toggleStar } = useStarred()
  const [searchParams, setSearchParams] = useSearchParams()
  const [showStarredOnly, setShowStarredOnly] = useState(false)
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [treeVisible, setTreeVisible] = useState(window.innerWidth >= 768)
  const isNarrow = typeof window !== 'undefined' && window.innerWidth < 768
  const [files, setFiles] = useState<FileItem[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list')
  const [treeVersion, setTreeVersion] = useState(0)
  const refreshTree = () => setTreeVersion(v => v + 1)
  const [previewFile, setPreviewFile] = useState<FileItem | null>(null)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; file: FileItem } | null>(null)
  const [movePickerOpen, setMovePickerOpen] = useState(false)
  const [moveTargetIds, setMoveTargetIds] = useState<number[]>([])
  const [detailFile, setDetailFile] = useState<FileItem | null>(null)
  const [recentFiles, setRecentFiles] = useState<FileItem[]>([])

  const displayFiles = useMemo(() => {
    let result = files
    if (showStarredOnly || typeFilter === 'starred') result = result.filter(f => isStarred(f.id))
    if (typeFilter === 'image') result = result.filter(f => f.mime_type.startsWith('image/'))
    else if (typeFilter === 'video') result = result.filter(f => f.mime_type.startsWith('video/'))
    else if (typeFilter === 'document') result = result.filter(f =>
      f.mime_type.includes('pdf') || f.mime_type.includes('text') || f.mime_type.includes('word') ||
      f.mime_type.includes('excel') || f.mime_type.includes('powerpoint') || f.mime_type.includes('json'))
    else if (typeFilter === 'archive') result = result.filter(f =>
      f.mime_type.includes('zip') || f.mime_type.includes('rar') || f.mime_type.includes('7z') ||
      f.mime_type.includes('tar') || f.mime_type.includes('gzip'))
    return result
  }, [files, showStarredOnly, typeFilter, isStarred])

  const parentId = searchParams.get('parent_id') ? Number(searchParams.get('parent_id')) : null
  const [breadcrumb, setBreadcrumb] = useState<{ id: number | null; name: string }[]>([{ id: null, name: '根目录' }])

  useEffect(() => {
    getBreadcrumb(parentId).then((res: any) => {
      setBreadcrumb(res.data || [{ id: null, name: '根目录' }])
    }).catch(() => {})
  }, [parentId])

  const fetchFiles = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await getFileList(parentId)
      setFiles(res.data?.items || res.data || [])
    } catch {
      // handled
    } finally {
      setLoading(false)
    }
  }, [parentId])

  useEffect(() => { fetchFiles() }, [fetchFiles])

  useEffect(() => {
    getRecentFiles(6).then((res: any) => setRecentFiles(res.data || [])).catch(() => {})
  }, [files])

  // Close context menu on outside click
  useEffect(() => {
    const close = () => setContextMenu(null)
    if (contextMenu) {
      window.addEventListener('click', close)
      return () => window.removeEventListener('click', close)
    }
  }, [contextMenu])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'Delete' && selectedRowKeys.length > 0) {
        handleBatchDelete()
      } else if (e.key === 'F2' && selectedRowKeys.length === 1) {
        const file = files.find(f => f.id === selectedRowKeys[0])
        if (file) handleRename(file)
      } else if (e.key === 'a' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        setSelectedRowKeys(files.map(f => f.id))
      } else if (e.key === 'Escape') {
        setSelectedRowKeys([])
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selectedRowKeys, files])

  const navigateTo = (id: number | null) => {
    if (id === null) {
      setSearchParams({})
    } else {
      setSearchParams({ parent_id: String(id) })
    }
  }

  const CHUNK_THRESHOLD = 10 * 1024 * 1024  // 10MB

  const handleUpload = async (fileList: any) => {
    const rawFiles: File[] = fileList.fileList?.map((f: any) => f.originFileObj) || [fileList.file]
    if (!rawFiles.length) return
    setUploading(true)
    setUploadProgress(0)
    try {
      // 分离小文件和大文件
      const small = rawFiles.filter(f => f.size <= CHUNK_THRESHOLD)
      const large = rawFiles.filter(f => f.size > CHUNK_THRESHOLD)

      // 小文件批量上传（一次请求）
      if (small.length > 0) {
        await uploadFiles(small, parentId, (p) => setUploadProgress(Math.round(p * 0.9)))
      }
      // 大文件逐个分片上传
      for (const file of large) {
        await uploadFileWithChunks(file, parentId, (p) =>
          setUploadProgress(Math.round(90 + (p / 10)))
        )
      }
      setUploadProgress(100)
      message.success(`上传完成: ${rawFiles.length} 个文件`)
      fetchFiles()
      refreshTree()
    } catch {
      // handled by interceptor
    } finally {
      setUploading(false)
      setUploadProgress(0)
    }
  }

  const handleMkdir = () => {
    Modal.confirm({
      title: '新建文件夹',
      content: <Input id="mkdir-input" placeholder="文件夹名称" />,
      onOk: async () => {
        const input = document.getElementById('mkdir-input') as HTMLInputElement
        if (input?.value) {
          await mkdir(input.value, parentId)
          message.success('创建成功')
          fetchFiles()
          refreshTree()
        }
      },
    })
  }

  const handleRename = (file: FileItem) => {
    let name = file.name
    Modal.confirm({
      title: '重命名',
      content: <Input defaultValue={file.name} onChange={(e) => { name = e.target.value }} />,
      onOk: async () => {
        await renameFile(file.id, name)
        message.success('重命名成功')
        fetchFiles()
        refreshTree()
      },
    })
  }

  const handleDelete = (id: number) => {
    Modal.confirm({
      title: '确认删除',
      content: '文件将移到回收站',
      onOk: async () => {
        const file = files.find(f => f.id === id)
        await deleteFile(id)
        fetchFiles()
        refreshTree()
        message.success({
          content: `已移入回收站: ${file?.name || id}`,
          duration: 5,
          key: `delete_${id}`,
        })
      },
    })
  }

  const handleBatchDelete = () => {
    Modal.confirm({
      title: '确认批量删除',
      content: `将删除 ${selectedRowKeys.length} 个文件`,
      onOk: async () => {
        for (const id of selectedRowKeys) await deleteFile(id)
        message.success('删除完成')
        setSelectedRowKeys([])
        fetchFiles()
      },
    })
  }

  const handleShare = async (file: FileItem) => {
    Modal.confirm({
      title: '创建分享链接',
      content: (
        <div>
          <Input placeholder="提取码（可选）" id="share-pwd" style={{ marginBottom: 8 }} />
          <Input placeholder="有效期（小时，0=永久）" id="share-expire" defaultValue="0" style={{ marginBottom: 8 }} />
          <Input placeholder="下载次数限制（0=不限）" id="share-max-dl" defaultValue="0" />
        </div>
      ),
      onOk: async () => {
        const pwd = (document.getElementById('share-pwd') as HTMLInputElement)?.value || ''
        const expire = Number((document.getElementById('share-expire') as HTMLInputElement)?.value) || 0
        const maxDl = Number((document.getElementById('share-max-dl') as HTMLInputElement)?.value) || 0
        const res: any = await createShare(file.id, pwd, expire, maxDl)
        const shareUrl = `${window.location.origin}/s/${res.data.code}`
        Modal.success({
          title: '分享链接已生成',
          width: 420,
          content: (
            <div style={{ textAlign: 'center' }}>
              <img
                src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(shareUrl)}`}
                alt="QR Code"
                style={{ width: 180, height: 180, marginBottom: 12, borderRadius: 8 }}
              />
              <Input value={shareUrl} readOnly onClick={(e) => (e.target as HTMLInputElement).select()} />
              <div style={{ marginTop: 4, color: '#999', fontSize: 11 }}>扫码即可访问分享文件</div>
            </div>
          ),
        })
      },
    })
  }

  const handleMoveClick = (ids: number[]) => {
    setMoveTargetIds(ids)
    setMovePickerOpen(true)
  }

  const handleMoveConfirm = async (targetId: number | null) => {
    setMovePickerOpen(false)
    if (moveTargetIds.length === 0) return
    await moveFiles(moveTargetIds, targetId)
    message.success(`已移动 ${moveTargetIds.length} 个文件`)
    setSelectedRowKeys([])
    fetchFiles()
    refreshTree()
  }

  const handleCopy = async (file: FileItem) => {
    await copyFile(file.id, parentId)
    message.success(`已复制: ${file.name}`)
    fetchFiles()
    refreshTree()
  }

  const menuItemStyle: React.CSSProperties = {
    padding: '8px 16px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, fontSize: 13,
    transition: 'background 0.2s',
  }

  const handleBatchRename = () => {
    let pat = '{name}_{n}{ext}'
    Modal.confirm({
      title: '批量重命名',
      content: (
        <div>
          <p style={{ color: '#666', fontSize: 12, marginBottom: 8 }}>
            占位符：<code>{'{name}'}</code>=原名 <code>{'{n}'}</code>=序号 <code>{'{ext}'}</code>=扩展名
          </p>
          <Input defaultValue="{name}_{n}{ext}" onChange={(e) => { pat = e.target.value }} />
          <p style={{ color: '#999', fontSize: 11, marginTop: 4 }}>
            例如 "照片_{'{n}'}{'{ext}'}" → 照片_1.jpg, 照片_2.png
          </p>
        </div>
      ),
      onOk: async () => {
        await batchRename(selectedRowKeys, pat)
        message.success('批量重命名完成')
        setSelectedRowKeys([])
        fetchFiles()
        refreshTree()
      },
    })
  }

  const handleImportUrl = () => {
    let url = ''
    let fname = ''
    Modal.confirm({
      title: '从 URL 导入文件',
      content: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input placeholder="https://example.com/file.pdf" onChange={(e) => { url = e.target.value }} />
          <Input placeholder="文件名（可选，自动从URL提取）" onChange={(e) => { fname = e.target.value }} />
        </Space>
      ),
      onOk: async () => {
        if (!url.trim()) { message.error('请输入 URL'); return Promise.reject() }
        await importFromUrl(url.trim(), fname.trim() || undefined, parentId)
        message.success('导入成功')
        fetchFiles()
        refreshTree()
      },
    })
  }

  const handlePasswordChange = () => {
    let oldPwd = '', newPwd = ''
    Modal.confirm({
      title: '修改密码',
      content: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input.Password placeholder="原密码" onChange={(e) => { oldPwd = e.target.value }} />
          <Input.Password placeholder="新密码（至少6位）" onChange={(e) => { newPwd = e.target.value }} />
        </Space>
      ),
      onOk: async () => {
        await changePassword(oldPwd, newPwd)
        message.success('密码修改成功，请重新登录')
      },
    })
  }

  const handleDownload = (file: FileItem) => {
    const a = document.createElement('a')
    a.href = getDownloadUrl(file.id)
    a.download = file.name
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const handlePreview = (file: FileItem) => {
    setPreviewFile(file)
  }

  const handleSearch = async () => {
    if (!searchKeyword.trim()) { fetchFiles(); return }
    setLoading(true)
    try {
      const res: any = await searchFiles({ keyword: searchKeyword })
      setFiles(res.data?.items || res.data || [])
    } catch { /* handled */ }
    finally { setLoading(false) }
  }

  const getFileIcon = (file: FileItem) => {
    if (file.is_dir) return <FolderOutlined style={{ fontSize: 20, color: '#faad14' }} />
    const ext = file.name.split('.').pop()?.toLowerCase() || ''
    if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'ico'].includes(ext)) return <FileOutlined style={{ fontSize: 20, color: '#52c41a' }} />
    if (['mp4', 'avi', 'mkv', 'mov', 'webm'].includes(ext)) return <FileOutlined style={{ fontSize: 20, color: '#722ed1' }} />
    if (['mp3', 'wav', 'flac', 'ogg', 'aac'].includes(ext)) return <FileOutlined style={{ fontSize: 20, color: '#eb2f96' }} />
    if (['pdf'].includes(ext)) return <FileOutlined style={{ fontSize: 20, color: '#ff4d4f' }} />
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return <FileOutlined style={{ fontSize: 20, color: '#fa8c16' }} />
    if (['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext)) return <FileOutlined style={{ fontSize: 20, color: '#1890ff' }} />
    if (['py', 'js', 'ts', 'jsx', 'tsx', 'java', 'go', 'rs', 'cpp', 'c', 'h'].includes(ext)) return <FileOutlined style={{ fontSize: 20, color: '#13c2c2' }} />
    if (['md', 'txt', 'json', 'xml', 'yaml', 'yml', 'csv'].includes(ext)) return <FileOutlined style={{ fontSize: 20, color: '#8c8c8c' }} />
    return <FileOutlined style={{ fontSize: 20, color: '#bfbfbf' }} />
  }

  const columns: ColumnsType<FileItem> = [
    {
      title: '名称', dataIndex: 'name', key: 'name', sorter: (a: FileItem, b: FileItem) => a.name.localeCompare(b.name),
      render: (_, record) => (
        <Space
          style={{ cursor: record.is_dir ? 'pointer' : 'default' }}
          onClick={() => record.is_dir && navigateTo(record.id)}
        >
          <span onClick={(e) => { e.stopPropagation(); toggleStar(record.id) }} style={{ cursor: 'pointer' }}>
            {isStarred(record.id) ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined style={{ opacity: 0.3 }} />}
          </span>
          {getFileIcon(record)}
          <span style={{ color: record.is_dir ? '#1890ff' : 'inherit' }}>{record.name}</span>
        </Space>
      ),
    },
    { title: '大小', dataIndex: 'file_size', key: 'size', sorter: (a: FileItem, b: FileItem) => a.file_size - b.file_size, render: (s: number, r: FileItem) => r.is_dir ? '-' : formatBytes(s), width: 120 },
    { title: '类型', dataIndex: 'mime_type', key: 'mime', render: (t: string, r: FileItem) => r.is_dir ? '文件夹' : t, width: 150 },
    { title: '修改时间', dataIndex: 'updated_at', key: 'time', sorter: (a: FileItem, b: FileItem) => new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime(), defaultSortOrder: 'descend', render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm'), width: 160 },
    { title: '下载', dataIndex: 'download_count', key: 'dl', sorter: (a: any, b: any) => (a.download_count || 0) - (b.download_count || 0), render: (_: any, r: FileItem) => r.is_dir ? '-' : (r as any).download_count || 0, width: 70 },
    {
      title: '操作', key: 'action', width: 280,
      render: (_, record) => (
        <Space>
          {!record.is_dir && <Button size="small" icon={<EyeOutlined />} onClick={() => handlePreview(record)}>预览</Button>}
          {!record.is_dir && <Button size="small" icon={<DownloadOutlined />} onClick={() => handleDownload(record)}>下载</Button>}
          <Button size="small" icon={<ShareAltOutlined />} onClick={() => handleShare(record)}>分享</Button>
          <Dropdown menu={{
            items: [
              { key: 'rename', icon: <EditOutlined />, label: '重命名', onClick: () => handleRename(record) },
              { key: 'copy', icon: <CopyOutlined />, label: '复制', onClick: () => handleCopy(record) },
              { key: 'delete', icon: <DeleteOutlined />, label: '删除', danger: true, onClick: () => handleDelete(record.id) },
            ],
          }}>
            <Button size="small">更多</Button>
          </Dropdown>
        </Space>
      ),
    },
  ]

  return (
    <>
    <Layout style={{ background: '#fff', minHeight: 400 }}>
      {treeVisible && (
        <Sider width={220} style={{ background: '#fafafa', borderRight: '1px solid #f0f0f0', padding: '8px 0' }}>
          <div style={{ padding: '8px 16px', fontWeight: 'bold', borderBottom: '1px solid #f0f0f0', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
            目录导航
            <Button type="text" size="small" onClick={() => setTreeVisible(false)}>✕</Button>
          </div>
          <DirectoryTree
            onSelect={(id) => { navigateTo(id); if (window.innerWidth < 768) setTreeVisible(false) }}
            selectedId={parentId}
            refreshKey={treeVersion}
            onDropFile={async (fileId, targetId) => {
              await moveFiles([fileId], targetId)
              message.success('文件已移动')
              fetchFiles()
              refreshTree()
            }}
          />
          <div style={{ borderTop: '1px solid #f0f0f0' }}>
            <RecentActivity refreshKey={treeVersion} />
          </div>
        </Sider>
      )}
      <LayoutContent style={{ padding: '0 16px' }}>
      {/* Toolbar */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <Space>
          <span style={{ fontSize: 13, color: '#999', marginLeft: 8 }}>
            {displayFiles.length} 项
            {typeFilter !== 'all' && ` · ${typeFilter}`}
          </span>
          <Upload.Dragger
            showUploadList={false}
            multiple
            onChange={handleUpload}
            style={{ display: 'inline-block', minWidth: 120 }}
          >
            <Button type="primary" icon={<UploadOutlined />} loading={uploading}>
              上传文件（支持拖拽）
            </Button>
          </Upload.Dragger>
          <Button icon={<LinkOutlined />} onClick={handleImportUrl}>URL导入</Button>
          <Button icon={<FolderAddOutlined />} onClick={handleMkdir}>新建文件夹</Button>
          <Button icon={<FileOutlined />} onClick={() => {
            let fname = ''
            Modal.confirm({
              title: '新建文本文件',
              content: <Input placeholder="文件名（默认加 .txt）" onChange={(e) => { fname = e.target.value }} />,
              onOk: async () => {
                if (!fname.trim()) { message.error('请输入文件名'); return Promise.reject() }
                await touchFile(fname.trim(), '', parentId)
                message.success(`已创建: ${fname}`)
                fetchFiles()
                refreshTree()
              },
            })
          }}>新建文件</Button>
          {selectedRowKeys.length > 0 && (() => {
            const totalSize = displayFiles.filter(f => selectedRowKeys.includes(f.id) && !f.is_dir).reduce((s, f) => s + f.file_size, 0)
            const sizeStr = totalSize > 1073741824 ? `${(totalSize / 1073741824).toFixed(2)} GB` :
              totalSize > 1048576 ? `${(totalSize / 1048576).toFixed(1)} MB` :
              totalSize > 1024 ? `${(totalSize / 1024).toFixed(1)} KB` : `${totalSize} B`
            return (
            <>
              <span style={{ fontSize: 12, color: '#666', alignSelf: 'center' }}>
                已选 {selectedRowKeys.length} 项 · {sizeStr}
              </span>
              <Button icon={<DownloadOutlined />} onClick={() => {
                batchDownload(selectedRowKeys).then(() => message.success('ZIP 下载已开始'))
              }}>
                打包下载({selectedRowKeys.length})
              </Button>
              <Button icon={<EditOutlined />} onClick={handleBatchRename}>
                批量重命名({selectedRowKeys.length})
              </Button>
              <Button icon={<FolderOpenOutlined />} onClick={() => handleMoveClick(selectedRowKeys)}>
                移动到({selectedRowKeys.length})
              </Button>
              <Button danger icon={<DeleteOutlined />} onClick={handleBatchDelete}>
                删除选中({selectedRowKeys.length})
              </Button>
            </>
            )
          })()}
          {uploading && <Progress percent={uploadProgress} size="small" style={{ width: 100 }} />}
        </Space>
        <Space>
          <Button
            type={treeVisible ? 'primary' : 'default'}
            icon={<FolderOutlined />}
            onClick={() => setTreeVisible(!treeVisible)}
          />
          <Button
            icon={viewMode === 'list' ? <AppstoreOutlined /> : <UnorderedListOutlined />}
            onClick={() => setViewMode(viewMode === 'list' ? 'grid' : 'list')}
          />
          <Button
            type={showStarredOnly ? 'primary' : 'default'}
            icon={showStarredOnly ? <StarFilled /> : <StarOutlined />}
            onClick={() => setShowStarredOnly(!showStarredOnly)}
          />
          <Button icon={<KeyOutlined />} onClick={handlePasswordChange}>修改密码</Button>
          <Input.Search
            placeholder="搜索文件..."
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            onSearch={handleSearch}
            style={{ width: 250 }}
          />
          <Button icon={<ReloadOutlined />} onClick={fetchFiles} />
        </Space>
      </div>

      {/* Storage quota warning */}
      {user && user.storage_quota > 0 && (() => {
        const pct = (user.storage_used / user.storage_quota) * 100
        if (pct > 90) return <Alert type="error" banner message={`存储空间已使用 ${pct.toFixed(1)}%，请及时清理！`} style={{ marginBottom: 12 }} />
        if (pct > 70) return <Alert type="warning" banner message={`存储空间已使用 ${pct.toFixed(1)}%，建议清理不需要的文件`} style={{ marginBottom: 12 }} />
        return null
      })()}

      {/* Quick type filter */}
      <Segmented
        options={[
          { label: '全部', value: 'all' },
          { label: '🖼 图片', value: 'image' },
          { label: '🎬 视频', value: 'video' },
          { label: '📄 文档', value: 'document' },
          { label: '📦 压缩包', value: 'archive' },
          { label: '⭐ 收藏', value: 'starred' },
        ]}
        value={typeFilter}
        onChange={(v) => { setTypeFilter(v as string); setShowStarredOnly(v === 'starred') }}
        style={{ marginBottom: 12 }}
      />

      {/* Recent files */}
      {recentFiles.length > 0 && typeFilter === 'all' && !showStarredOnly && parentId === null && (
        <div style={{ marginBottom: 16, padding: '12px 16px', background: '#fafafa', borderRadius: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 'bold', color: '#999', marginBottom: 8, textTransform: 'uppercase' }}>
            🕐 最近访问
          </div>
          <Space wrap size={[8, 8]}>
            {recentFiles.map((f: any) => (
              <Tag
                key={f.id}
                style={{ cursor: 'pointer', padding: '4px 10px', fontSize: 13 }}
                onClick={() => setDetailFile(f)}
              >
                <FileOutlined /> {f.name.length > 28 ? f.name.slice(0, 26) + '...' : f.name}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {/* Breadcrumb */}
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={breadcrumb.map((item, idx) => ({
          title: idx === breadcrumb.length - 1 ? (
            <span>{item.name}</span>
          ) : (
            <a onClick={() => navigateTo(item.id)}>{item.name}</a>
          ),
        }))}
      />

      {/* File Table / Grid View */}
      {viewMode === 'grid' ? (
        <Row gutter={[16, 16]}>
          {displayFiles.map((f) => (
            <Col key={f.id} xs={12} sm={8} md={6} lg={4} xl={3}>
              <Card
                hoverable
                size="small"
                style={{ textAlign: 'center', cursor: f.is_dir ? 'pointer' : 'default' }}
                onClick={() => setDetailFile(f)}
                onDoubleClick={() => f.is_dir && navigateTo(f.id)}
                onContextMenu={(e) => { e.preventDefault(); setContextMenu({ x: e.clientX, y: e.clientY, file: f }) }}
                draggable
                onDragStart={(e: React.DragEvent) => { e.dataTransfer.setData('text/plain', String(f.id)); e.dataTransfer.effectAllowed = 'move' }}
                cover={
                  <div style={{ fontSize: 48, padding: '16px 0', background: '#fafafa' }}>
                    {getFileIcon(f)}
                  </div>
                }
                actions={[
                  !f.is_dir && <EyeOutlined key="preview" onClick={() => handlePreview(f)} />,
                  !f.is_dir && <DownloadOutlined key="download" onClick={() => handleDownload(f)} />,
                  <ShareAltOutlined key="share" onClick={() => handleShare(f)} />,
                  <DeleteOutlined key="delete" onClick={() => handleDelete(f.id)} />,
                ].filter(Boolean)}
              >
                <Card.Meta
                  title={f.name.length > 20 ? f.name.slice(0, 18) + '...' : f.name}
                  description={f.is_dir ? '文件夹' : formatBytes(f.file_size)}
                />
              </Card>
            </Col>
          ))}
          {displayFiles.length === 0 && <Col span={24}><Empty description={files.length === 0 ? '此目录为空' : '筛选结果为空'} /></Col>}
        </Row>
      ) : (
        <Table
        rowKey="id"
        columns={columns}
        dataSource={displayFiles}
        loading={loading}
        sticky={{ offsetHeader: 0 }}
        rowSelection={{
          selectedRowKeys,
          onChange: (keys) => setSelectedRowKeys(keys as number[]),
        }}
        pagination={{ pageSize: 50, showSizeChanger: false }}
        locale={{ emptyText: <Empty description="此目录为空" /> }}
        onRow={(record) => ({
          onClick: () => setDetailFile(record),
          onDoubleClick: () => record.is_dir && navigateTo(record.id),
          onContextMenu: (e) => { e.preventDefault(); setContextMenu({ x: e.clientX, y: e.clientY, file: record }) },
          draggable: true,
          onDragStart: (e: React.DragEvent) => {
            e.dataTransfer.setData('text/plain', String(record.id))
            e.dataTransfer.effectAllowed = 'move'
          },
        })}
      />
      )}
      </LayoutContent>
    </Layout>
    <PreviewModal
      open={!!previewFile}
      file={previewFile}
      onClose={() => setPreviewFile(null)}
      siblingImages={displayFiles.filter(f => !f.is_dir && ['jpg','jpeg','png','gif','bmp','webp','svg'].includes(f.name.split('.').pop()?.toLowerCase() || '')).map(f => ({ id: f.id, name: f.name }))}
      onNavigate={(id) => setPreviewFile(displayFiles.find(f => f.id === id) || null)}
    />
    <FileDetail
      file={detailFile}
      open={!!detailFile}
      onClose={() => setDetailFile(null)}
      onPreview={(f) => { setDetailFile(null); setPreviewFile(f) }}
      onDownload={handleDownload}
      onShare={handleShare}
      onRename={handleRename}
      onDelete={handleDelete}
    />
    <FolderPicker
      open={movePickerOpen}
      onOk={handleMoveConfirm}
      onCancel={() => setMovePickerOpen(false)}
      title="选择目标文件夹"
    />
    {contextMenu && (
      <div
        style={{
          position: 'fixed', left: contextMenu.x, top: contextMenu.y, zIndex: 1000,
          background: 'var(--bg, #fff)', border: '1px solid #d9d9d9', borderRadius: 8,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)', minWidth: 160, padding: '4px 0',
        }}
      >
        {contextMenu.file.is_dir && (
          <div style={menuItemStyle} onClick={() => { navigateTo(contextMenu.file.id); setContextMenu(null) }}>
            <FolderOpenOutlined /> 打开
          </div>
        )}
        {!contextMenu.file.is_dir && (
          <div style={menuItemStyle} onClick={() => { handlePreview(contextMenu.file); setContextMenu(null) }}>
            <EyeOutlined /> 预览
          </div>
        )}
        {!contextMenu.file.is_dir && (
          <div style={menuItemStyle} onClick={() => { handleDownload(contextMenu.file); setContextMenu(null) }}>
            <DownloadOutlined /> 下载
          </div>
        )}
        <div style={menuItemStyle} onClick={() => { handleShare(contextMenu.file); setContextMenu(null) }}>
          <ShareAltOutlined /> 分享
        </div>
        <div style={menuItemStyle} onClick={() => { handleRename(contextMenu.file); setContextMenu(null) }}>
          <EditOutlined /> 重命名
        </div>
        <div style={menuItemStyle} onClick={() => { handleMoveClick([contextMenu.file.id]); setContextMenu(null) }}>
          <FolderOpenOutlined /> 移动到...
        </div>
        <div style={menuItemStyle} onClick={() => { handleCopy(contextMenu.file); setContextMenu(null) }}>
          <CopyOutlined /> 复制
        </div>
        <div style={{ ...menuItemStyle, color: '#ff4d4f' }} onClick={() => { handleDelete(contextMenu.file.id); setContextMenu(null) }}>
          <DeleteOutlined /> 删除
        </div>
      </div>
    )}
    </>
  )
}
