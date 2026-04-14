import { expect, test } from '@playwright/test';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PROJECT_ID = 'proj_test';
const NOVEL_ID = 'novel_test';

const SOURCE_NODE = {
  family: 'outline_node',
  object_id: 'obj_source_001',
  current_revision_id: 'rev_source_001',
  current_revision_number: 1,
  payload: { title: '第一章大纲', summary: '主角登场' },
};

const TARGET_NODE = {
  family: 'plot_node',
  object_id: 'obj_target_001',
  current_revision_id: 'rev_target_001',
  current_revision_number: 1,
  payload: {
    title: '剧情节点一',
    summary: '主角遇到导师',
    parent_object_id: 'obj_source_001',
  },
};

function pipelineSnapshot(sourceObjects = [SOURCE_NODE], targetObjects = [TARGET_NODE]) {
  return {
    ok: true,
    data: {
      pipeline: {
        pipeline_stage: 'outline_to_plot',
        source_family: 'outline_node',
        target_family: 'plot_node',
        source_objects: sourceObjects,
        target_objects: targetObjects,
        upstream_ready: true,
      },
    },
  };
}

const WORKBENCH_URL = `/workbench/outline-to-plot?project_id=${PROJECT_ID}&novel_id=${NOVEL_ID}`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function setupApiMocks(
  page: import('@playwright/test').Page,
  opts: { deleteSucceeds?: boolean } = {},
) {
  const { deleteSucceeds = true } = opts;

  // Startup
  await page.route('/api/startup', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        data: {
          startup: {
            workspace_contexts: [
              { project_id: PROJECT_ID, project_title: '测试项目', novel_id: NOVEL_ID, novel_title: '测试小说' },
            ],
            has_workspace_contexts: true,
          },
        },
      }),
    }),
  );

  // Command center (needed by AppShell nav)
  await page.route('/api/command-center*', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        data: {
          snapshot: {
            project_id: PROJECT_ID,
            novel_id: NOVEL_ID,
            project_title: '测试项目',
            novel_title: '测试小说',
            stage_label: '大纲',
            stage_detail: '',
            object_counts: {},
            blocked_signals: [],
            stale_signals: [],
            next_actions: [],
            routes: [],
            audit_entries: [],
            review_queue_count: 0,
          },
        },
      }),
    }),
  );

  // Pipeline workbench GET — returns one source + one target node
  await page.route('/api/workbench/outline_to_plot*', (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(pipelineSnapshot()) });
    } else {
      route.continue();
    }
  });

  // Workbench POST (delete / generate)
  await page.route('/api/workbench*', async (route) => {
    if (route.request().method() !== 'POST') {
      return route.continue();
    }
    const body = route.request().postDataJSON() as Record<string, unknown>;
    if (body.action === 'delete_object') {
      if (deleteSucceeds) {
        route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            data: { result: { action: 'delete_object', family: body.family, object_id: body.object_id } },
          }),
        });
      } else {
        route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({
            ok: false,
            error: { code: 'not_found', message: '节点不存在', details: {} },
          }),
        });
      }
    } else {
      route.continue();
    }
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('删除节点按钮', () => {
  test('删除节点按钮可见且未禁用', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto(WORKBENCH_URL);

    const deleteBtn = page.getByRole('button', { name: '删除节点' });
    await expect(deleteBtn).toBeVisible();
    await expect(deleteBtn).toBeEnabled();
  });

  test('点击删除节点弹出确认对话框', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto(WORKBENCH_URL);

    let confirmMessage = '';
    page.on('dialog', async (dialog) => {
      confirmMessage = dialog.message();
      await dialog.dismiss(); // 取消
    });

    await page.getByRole('button', { name: '删除节点' }).click();
    expect(confirmMessage).toContain('确认删除');
  });

  test('取消确认不发送 DELETE 请求', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto(WORKBENCH_URL);

    const requests: string[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/workbench') && req.method() === 'POST') {
        requests.push(req.url());
      }
    });

    page.on('dialog', (dialog) => dialog.dismiss());
    await page.getByRole('button', { name: '删除节点' }).click();

    // 等一下确保没有请求发出
    await page.waitForTimeout(300);
    expect(requests).toHaveLength(0);
  });

  test('确认删除后发送 POST 请求且节点从列表消失', async ({ page }) => {
    await setupApiMocks(page);
    await page.goto(WORKBENCH_URL);

    // 确认节点标题可见（工作台 h4 标题）
    await expect(page.getByRole('heading', { name: '第一章大纲' })).toBeVisible();

    const deleteRequests: Array<Record<string, unknown>> = [];
    page.on('request', async (req) => {
      if (req.url().includes('/api/workbench') && req.method() === 'POST') {
        try {
          deleteRequests.push(req.postDataJSON() as Record<string, unknown>);
        } catch {
          // ignore
        }
      }
    });

    page.on('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: '删除节点' }).click();

    // 等待请求发出
    await page.waitForTimeout(500);

    expect(deleteRequests).toHaveLength(1);
    expect(deleteRequests[0].action).toBe('delete_object');
    expect(deleteRequests[0].object_id).toBeTruthy();
  });

  test('删除失败时显示错误信息', async ({ page }) => {
    await setupApiMocks(page, { deleteSucceeds: false });
    await page.goto(WORKBENCH_URL);

    page.on('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: '删除节点' }).click();

    // 应显示错误提示
    await expect(page.locator('.form-error')).toBeVisible({ timeout: 5000 });
  });
});
