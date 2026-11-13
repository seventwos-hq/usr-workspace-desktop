#!/usr/bin/env node
/*
Copyright 2026 Element Creations Ltd.

SPDX-License-Identifier: AGPL-3.0-only
Please see LICENSE in the repository root for full details.
*/

/*
 * Checks for the presence of a webapp, inspects its version and sets the
 * version metadata of the package to match.
 */

import { promises as fs } from "node:fs";
import * as asar from "@electron/asar";
import path from "node:path";
import * as url from "node:url";

export async function versionFromAsar(): Promise<string> {
    try {
        await fs.stat("webapp.asar");
    } catch {
        throw new Error("No 'webapp.asar' found. Run 'pnpm run fetch'");
    }

    return asar.extractFile("webapp.asar", "version").toString().trim();
}

export async function setPackageVersion(ver: string): Promise<void> {
    // Set version in package.json: electron-builder uses this to populate all the various version fields.
    // We write the file directly rather than shelling out to `pnpm version`, as pnpm 11+ rejects the
    // `--new-version` flag (and `pnpm version` semantics differ between pnpm majors).
    const packageJsonPath = path.resolve(process.cwd(), "package.json");
    const raw = await fs.readFile(packageJsonPath, "utf-8");
    const packageJson = JSON.parse(raw);
    packageJson.version = ver;
    const indent = /^[ \t]+(?=")/m.exec(raw)?.[0] ?? "    ";
    await fs.writeFile(packageJsonPath, JSON.stringify(packageJson, null, indent) + (raw.endsWith("\n") ? "\n" : ""));
}

async function main(args: string[]): Promise<number> {
    let version = args[0];

    if (version === undefined) version = await versionFromAsar();

    await setPackageVersion(version);
    return 0;
}

if (import.meta.url.startsWith("file:")) {
    const modulePath = url.fileURLToPath(import.meta.url);
    if (process.argv[1] === modulePath) {
        main(process.argv.slice(2))
            .then((ret) => {
                process.exit(ret);
            })
            .catch((e) => {
                console.error(e);
                process.exit(1);
            });
    }
}
