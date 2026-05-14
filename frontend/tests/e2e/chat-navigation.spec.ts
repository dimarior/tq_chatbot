import { randomUUID } from "node:crypto";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const apiBaseURL = process.env.API_BASE_URL ?? "http://localhost:8000";

type SeededConversation = {
  assistantContent: string;
  threadId: string;
  title: string;
  userContent: string;
};

async function seedConversation(
  request: APIRequestContext,
  label: string,
): Promise<SeededConversation> {
  const threadId = randomUUID();
  const title = `E2E ${label} ${Date.now()}`;
  const userContent = `Mensaje usuario ${label} ${randomUUID().slice(0, 8)}`;
  const assistantContent = `Respuesta asistente ${label} ${randomUUID().slice(0, 8)}`;

  const userRes = await request.post(`${apiBaseURL}/api/threads/${threadId}/messages`, {
    data: {
      message: {
        role: "user",
        content: userContent,
        sources: null,
      },
      parentId: null,
    },
  });
  expect(userRes.ok()).toBeTruthy();

  const assistantRes = await request.post(
    `${apiBaseURL}/api/threads/${threadId}/messages`,
    {
      data: {
        message: {
          role: "assistant",
          content: assistantContent,
          sources: [
            {
              url: "https://example.com/e2e-source",
              title: "E2E Source",
              score: 1,
            },
          ],
        },
        parentId: null,
      },
    },
  );
  expect(assistantRes.ok()).toBeTruthy();

  const patchRes = await request.patch(`${apiBaseURL}/api/threads/${threadId}`, {
    data: { title },
  });
  expect(patchRes.status()).toBe(204);

  return { assistantContent, threadId, title, userContent };
}

async function deleteConversation(request: APIRequestContext, threadId: string) {
  const res = await request.delete(`${apiBaseURL}/api/threads/${threadId}`);
  expect(res.status()).toBe(204);
}

async function recentTitles(page: Page) {
  const labels = await page.locator("aside button").allTextContents();
  return labels
    .map((text) => text.trim())
    .filter((text) => text && text !== "Nueva conversación" && text !== "Archivar");
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test("opens a recent chat and loads its history", async ({ page, request }) => {
  const seeded = await seedConversation(request, "recent");

  try {
    await page.goto("/chat");
    await page.getByRole("button", { name: seeded.title }).click();

    await expect(page).toHaveURL(new RegExp(`/chat/${seeded.threadId}$`));
    await expect(page.getByText(seeded.userContent)).toBeVisible();
    await expect(page.getByText(seeded.assistantContent)).toBeVisible();
  } finally {
    await deleteConversation(request, seeded.threadId);
  }
});

test("keeps recent chats in stable order when opening an older chat", async ({
  page,
  request,
}) => {
  const older = await seedConversation(request, "older");
  const newer = await seedConversation(request, "newer");

  try {
    await page.goto("/chat");

    await expect.poll(async () => (await recentTitles(page)).slice(0, 2)).toEqual([
      newer.title,
      older.title,
    ]);

    await page.getByRole("button", { name: older.title }).click();

    await expect(page).toHaveURL(new RegExp(`/chat/${older.threadId}$`));
    await expect(page.getByText(older.assistantContent)).toBeVisible();
    await expect.poll(async () => (await recentTitles(page)).slice(0, 2)).toEqual([
      newer.title,
      older.title,
    ]);
  } finally {
    await deleteConversation(request, newer.threadId);
    await deleteConversation(request, older.threadId);
  }
});

test("starts a blank conversation from a recent chat", async ({ page, request }) => {
  const seeded = await seedConversation(request, "new-chat");

  try {
    await page.goto(`/chat/${seeded.threadId}`);
    await expect(page.getByText(seeded.assistantContent)).toBeVisible();

    await page.getByTestId("new-chat-button").click();

    await expect(page).toHaveURL(/\/chat$/);
    await expect(page.getByTestId("thread-loading-state")).toHaveCount(0);
    await expect(
      page.getByRole("textbox", { name: "Pregunta sobre Tecnoquímicas..." }),
    ).toBeVisible();
    await expect(
      page.getByRole("textbox", { name: "Pregunta sobre Tecnoquímicas..." }),
    ).toHaveValue("");
    await expect(page.getByText(seeded.userContent)).toHaveCount(0);
    await expect(page.getByText(seeded.assistantContent)).toHaveCount(0);
  } finally {
    await deleteConversation(request, seeded.threadId);
  }
});

test("creates a thread id only after the first message is sent", async ({ page }) => {
  await page.goto("/chat");
  await expect(page).toHaveURL(/\/chat$/);

  await page.getByTestId("new-chat-button").click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(
    page.getByRole("heading", { name: "¿En qué puedo ayudarte hoy?" }),
  ).toBeVisible();

  const createThreadResponse = page.waitForResponse((response) => {
    return (
      response.request().method() === "POST" &&
      response.url() === `${apiBaseURL}/api/threads`
    );
  });

  await page
    .getByRole("textbox", { name: "Pregunta sobre Tecnoquímicas..." })
    .fill("que es tqfarma");
  await page.getByRole("button", { name: "Enviar" }).click();

  const createThreadBody = (await createThreadResponse).json() as Promise<{ id: string }>;
  const { id: threadId } = await createThreadBody;
  await expect(page).toHaveURL(new RegExp(`/chat/${threadId}$`), {
    timeout: 30_000,
  });
  await expect(page.getByText("que es tqfarma")).toBeVisible();
});

test("reloading a saved chat does not create draft threads or refetch in a loop", async ({
  page,
  request,
}) => {
  const seeded = await seedConversation(request, "reload");
  const requestCounts = {
    createThread: 0,
    loadMessages: 0,
  };

  page.on("requestfinished", (req) => {
    const url = req.url();
    if (req.method() === "POST" && url === `${apiBaseURL}/api/threads`) {
      requestCounts.createThread += 1;
    }
    if (
      req.method() === "GET" &&
      url === `${apiBaseURL}/api/threads/${seeded.threadId}/messages`
    ) {
      requestCounts.loadMessages += 1;
    }
  });

  try {
    await page.goto(`/chat/${seeded.threadId}`);
    await expect(page.getByText(seeded.assistantContent)).toBeVisible();

    requestCounts.createThread = 0;
    requestCounts.loadMessages = 0;

    await page.reload();
    await expect(page).toHaveURL(new RegExp(`/chat/${seeded.threadId}$`));
    await expect(page.getByText(seeded.userContent)).toBeVisible();
    await expect(page.getByText(seeded.assistantContent)).toBeVisible();
    await page.waitForTimeout(1000);
    const settledLoadCount = requestCounts.loadMessages;
    await page.waitForTimeout(1500);

    expect(requestCounts.createThread).toBe(0);
    expect(requestCounts.loadMessages).toBeGreaterThanOrEqual(1);
    expect(requestCounts.loadMessages).toBe(settledLoadCount);
  } finally {
    await deleteConversation(request, seeded.threadId);
  }
});

test("switching between two existing chats settles the URL without an infinite loop", async ({
  page,
  request,
}) => {
  const alpha = await seedConversation(request, "loop-alpha");
  const beta = await seedConversation(request, "loop-beta");

  const messagesRequests: string[] = [];
  page.on("requestfinished", (req) => {
    if (req.method() !== "GET") return;
    const match = /\/api\/threads\/([0-9a-f-]+)\/messages$/.exec(req.url());
    if (match) messagesRequests.push(match[1]);
  });

  try {
    // Arrancamos DENTRO de un hilo existente: este es el escenario que
    // disparaba el loop infinito. El remoteId del runtime iba por detrás de la
    // URL y ThreadRouteSync lo reescribía al hilo viejo, peleando contra el
    // switch async de useRemoteThreadListRuntime.
    await page.goto(`/chat/${alpha.threadId}`);
    await expect(page.getByText(alpha.assistantContent)).toBeVisible();

    messagesRequests.length = 0;

    await page.getByRole("button", { name: beta.title }).click();

    // La URL debe estabilizarse en el hilo destino y NO rebotar al anterior.
    await expect(page).toHaveURL(new RegExp(`/chat/${beta.threadId}$`));
    await expect(page.getByText(beta.assistantContent)).toBeVisible();

    // Damos margen a que un posible loop se manifieste y reconfirmamos la URL.
    await page.waitForTimeout(1500);
    await expect(page).toHaveURL(new RegExp(`/chat/${beta.threadId}$`));
    await expect(page.getByText(beta.assistantContent)).toBeVisible();

    // Sin loop: el hilo destino se hidrata un número acotado de veces y el
    // hilo de origen no se vuelve a pedir tras conmutar.
    const betaCount = messagesRequests.filter((id) => id === beta.threadId).length;
    const alphaCount = messagesRequests.filter((id) => id === alpha.threadId).length;
    expect(betaCount).toBeGreaterThanOrEqual(1);
    expect(betaCount).toBeLessThanOrEqual(2);
    expect(alphaCount).toBeLessThanOrEqual(1);
  } finally {
    await deleteConversation(request, alpha.threadId);
    await deleteConversation(request, beta.threadId);
  }
});

test("archiving the active chat returns to the blank /chat route", async ({
  page,
  request,
}) => {
  const seeded = await seedConversation(request, "archive-active");

  try {
    await page.goto(`/chat/${seeded.threadId}`);
    await expect(page.getByText(seeded.assistantContent)).toBeVisible();

    await page.getByRole("button", { name: seeded.title }).hover();
    await page.getByRole("button", { name: "Archivar" }).click();

    await expect(page).toHaveURL(/\/chat$/);
    await expect(
      page.getByRole("heading", { name: "¿En qué puedo ayudarte hoy?" }),
    ).toBeVisible();
    await expect(page.getByText(seeded.assistantContent)).toHaveCount(0);
  } finally {
    try {
      const cleanup = await request.delete(`${apiBaseURL}/api/threads/${seeded.threadId}`);
      expect([204, 404]).toContain(cleanup.status());
    } catch {
      // El flujo principal ya archivó el hilo; si el cleanup falla por un
      // socket transitorio no debe falsear el resultado del test.
    }
  }
});

test("switching chats shows a loading state instead of the empty welcome flicker", async ({
  page,
  request,
}) => {
  const older = await seedConversation(request, "switch-old");
  const newer = await seedConversation(request, "switch-new");
  let unblockMessages!: () => void;
  let targetRequestSeen!: () => void;
  const allowMessages = new Promise<void>((resolve) => {
    unblockMessages = resolve;
  });
  const waitForTargetRequest = new Promise<void>((resolve) => {
    targetRequestSeen = resolve;
  });

  await page.route(`${apiBaseURL}/api/threads/${older.threadId}/messages`, async (route) => {
    targetRequestSeen();
    await allowMessages;
    await route.continue();
  });

  try {
    await page.goto(`/chat/${newer.threadId}`);
    await expect(page.getByText(newer.assistantContent)).toBeVisible();

    await page.getByRole("button", { name: older.title }).click();
    await waitForTargetRequest;

    await expect(page.getByTestId("thread-loading-state")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "¿En qué puedo ayudarte hoy?" }),
    ).toHaveCount(0);

    unblockMessages();

    await expect(page).toHaveURL(new RegExp(`/chat/${older.threadId}$`));
    await expect(page.getByText(older.assistantContent)).toBeVisible();
  } finally {
    await page.unroute(`${apiBaseURL}/api/threads/${older.threadId}/messages`);
    await deleteConversation(request, newer.threadId);
    await deleteConversation(request, older.threadId);
  }
});

test("shows loading and sources while responding, then persists title and history after refresh", async ({
  page,
  request,
}) => {
  let threadId: string | null = null;

  try {
    await page.goto("/chat");
    await page.getByTestId("new-chat-button").click();
    await expect(page).toHaveURL(/\/chat$/);

    const createThreadResponse = page.waitForResponse((response) => {
      return (
        response.request().method() === "POST" &&
        response.url() === `${apiBaseURL}/api/threads`
      );
    });

    await page
      .getByRole("textbox", { name: "Pregunta sobre Tecnoquímicas..." })
      .fill("que es tecnoquimicas?");
    await page.getByRole("button", { name: "Enviar" }).click();

    await expect(page.getByLabel("TQ-Asistente está escribiendo")).toBeVisible();
    await expect(page.getByText("Fuentes", { exact: true })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.locator("main a").first()).toBeVisible();

    const createThreadBody = (await createThreadResponse).json() as Promise<{ id: string }>;
    threadId = (await createThreadBody).id;

    await expect(page).toHaveURL(new RegExp(`/chat/${threadId}$`), {
      timeout: 30_000,
    });
    await expect(page.getByLabel("TQ-Asistente está escribiendo")).toHaveCount(0, {
      timeout: 30_000,
    });

    await expect(page.locator("main")).toContainText(/tqfarma|Tecnoquímicas/i, {
      timeout: 30_000,
    });

    await expect
      .poll(async () => {
        const titles = await recentTitles(page);
        return titles[0] ?? null;
      }, { timeout: 30_000 })
      .not.toBe("Nueva conversación");

    const currentTitle = (await recentTitles(page))[0]!;
    expect(currentTitle).not.toBe("Nueva conversación");

    await page.reload();
    await expect(page).toHaveURL(new RegExp(`/chat/${threadId}$`));
    await expect(page.getByText("que es tecnoquimicas?")).toBeVisible();
    await expect(page.locator("main")).toContainText(/tqfarma|Tecnoquímicas/i);
    await expect(page.getByText("Fuentes", { exact: true })).toBeVisible();
    await expect(page.locator("main a").first()).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: new RegExp(`^${escapeRegExp(currentTitle)}$`),
      }).first(),
    ).toBeVisible();
  } finally {
    if (threadId) {
      await deleteConversation(request, threadId);
    }
  }
});
