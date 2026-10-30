import { expect, test } from "@playwright/test";

test("la SPA se charge et navigue entre les vues", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("vidéothèque");
  await expect(page.getByText("Dossier à analyser")).toBeVisible();
  await expect(page.getByText("Serveur prêt")).toBeVisible();

  await page.getByRole("link", { name: "Matériel" }).click();
  await expect(page.getByRole("heading", { name: "Matériel & estimation" })).toBeVisible();
  await expect(page.getByText("Encodeurs AV1 détectés")).toBeVisible();

  await page.getByRole("link", { name: "Historique" }).click();
  await expect(page.getByRole("heading", { name: "Historique des analyses" })).toBeVisible();

  await page.getByRole("link", { name: "Compression", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("vidéothèque");

  expect(errors).toEqual([]);
});
