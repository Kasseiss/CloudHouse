import client from './client'

export const getFileList = (parentId?: number | null, page = 1, pageSize = 50) =>
  client.get('/files', { params: { parent_id: parentId, page, page_size: pageSize } })

export async function batchDownload(fileIds: number[]) {
  const token = localStorage.getItem('token')
  const resp = await fetch('/api/v1/files/batch-download', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(fileIds),
  })
  if (!resp.ok) throw new Error('Download failed')
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'clouddisk_batch.zip'
  a.click()
  URL.revokeObjectURL(url)
}

export const getBreadcrumb = (fileId?: number | null) =>
  client.get('/files/breadcrumb', { params: { file_id: fileId } })

export const getFileNotes = (fileId: number) =>
  client.get(`/files/${fileId}/notes`)

export const addFileNote = (fileId: number, content: string) => {
  const form = new FormData()
  form.append('content', content)
  return client.post(`/files/${fileId}/notes`, form)
}

export const deleteFileNote = (noteId: number) =>
  client.delete(`/files/notes/${noteId}`)

export const importFromUrl = (url: string, filename?: string, parentId?: number | null) => {
  const form = new FormData()
  form.append('url', url)
  if (filename) form.append('filename', filename)
  if (parentId != null) form.append('parent_id', String(parentId))
  return client.post('/files/import-url', form)
}

export const batchRename = (fileIds: number[], pattern: string) => {
  const form = new FormData()
  form.append('pattern', pattern)
  form.append('file_ids', fileIds.join(','))
  return client.post('/files/batch-rename', form)
}

export const getRecentFiles = (limit = 12) =>
  client.get('/files/recent', { params: { limit } })

export const getDirectoryTree = () => client.get('/files/tree')

export const getTrashList = (page = 1, pageSize = 200) =>
  client.get('/files/trash', { params: { page, page_size: pageSize } })

const CHUNK_SIZE = 10 * 1024 * 1024  // 10 MB per chunk

export const uploadFiles = (files: File[], parentId?: number | null, onProgress?: (p: number) => void) => {
  const formData = new FormData()
  files.forEach((f) => formData.append('files', f))
  if (parentId != null) formData.append('parent_id', String(parentId))
  return client.post('/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (e.total && onProgress) onProgress(Math.round((e.loaded * 100) / e.total))
    },
  })
}

export async function uploadFileWithChunks(
  file: File,
  parentId: number | null,
  onProgress?: (p: number) => void,
) {
  const totalChunks = Math.max(1, Math.ceil(file.size / CHUNK_SIZE))

  // Step 1: Initialize
  const initForm = new FormData()
  initForm.append('filename', file.name)
  initForm.append('total_size', String(file.size))
  initForm.append('total_chunks', String(totalChunks))
  if (parentId != null) initForm.append('parent_id', String(parentId))

  const initRes: any = await client.post('/files/upload/chunk/init', initForm)
  const uploadId = initRes.data.upload_id

  // Step 2: Upload chunks
  for (let i = 0; i < totalChunks; i++) {
    const start = i * CHUNK_SIZE
    const end = Math.min(start + CHUNK_SIZE, file.size)
    const blob = file.slice(start, end)

    const chunkForm = new FormData()
    chunkForm.append('chunk_index', String(i))
    chunkForm.append('chunk', blob, `chunk_${i}`)

    await client.post(`/files/upload/chunk/${uploadId}`, chunkForm)

    if (onProgress) {
      onProgress(Math.round(((i + 1) / totalChunks) * 90))  // 0-90% for uploading
    }
  }

  // Step 3: Complete
  if (onProgress) onProgress(95)
  const completeRes: any = await client.post(`/files/upload/chunk/${uploadId}/complete`)
  if (onProgress) onProgress(100)

  return completeRes
}

export const touchFile = (name: string, content?: string, parentId?: number | null) => {
  const form = new FormData()
  form.append('name', name)
  if (content) form.append('content', content)
  if (parentId != null) form.append('parent_id', String(parentId))
  return client.post('/files/touch', form)
}

export const mkdir = (name: string, parentId?: number | null) =>
  client.post('/files/mkdir', { name, parent_id: parentId })

export const renameFile = (id: number, name: string) =>
  client.put('/files/rename', { id, name })

export const moveFiles = (fileIds: number[], targetParentId: number | null) =>
  client.post('/files/move', { file_ids: fileIds, target_parent_id: targetParentId })

export const deleteFile = (id: number) => client.delete(`/files/${id}`)

export const restoreFile = (id: number) => client.post(`/files/${id}/restore`)

export const copyFile = (id: number, targetParentId?: number | null) =>
  client.post(`/files/${id}/copy`, null, { params: { target_parent_id: targetParentId } })

export const getTrashStats = () => client.get('/files/trash/stats')

export const emptyTrash = () => client.post('/files/trash/empty')

export const permanentDelete = (id: number) => client.delete(`/files/${id}/permanent`)

export const getDownloadUrl = (id: number) => `/api/v1/files/${id}/download`

export const getPreviewUrl = (id: number) => `/api/v1/files/${id}/preview`

export const searchFiles = (params: {
  keyword?: string
  file_type?: string
  start_time?: string
  end_time?: string
  page?: number
  page_size?: number
}) => client.get('/files/search', { params })
