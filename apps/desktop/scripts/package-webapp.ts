#!/usr/bin/env node
/*
Copyright 2026 Element Creations Ltd.

SPDX-License-Identifier: AGPL-3.0-only
Please see LICENSE in the repository root for full details.
*/

// Packs the web app built from this repository (apps/web/webapp) into webapp.asar for embedding in the desktop app.
// Nothing is downloaded: build the web app first with `pnpm --filter element-web build`.

import path from "node:path";
import { promises as fs } from "node:fs";
import * as asar from "@electron/asar";

import { setPackageVersion } from "./set-version.ts";

const ASAR_PATH = "webapp.asar";
const WEBAPP_DIR = path.resolve(import.meta.dirname, "../../web/webapp");

async function main(): Promise<number | undefined> {
    let cfgDir: string | undefined;
    let setVersion = true;

    for (let i = 2; i < process.argv.length; i++) {
        switch (process.argv[i]) {
            case "--cfgdir":
            case "-d":
                cfgDir = process.argv[++i];
                break;
            case "--no-set-version":
                setVersion = false;
                break;
            default:
                console.error(`Unknown argument ${process.argv[i]}`);
                return 1;
        }
    }

    if (cfgDir === undefined) {
        console.log("No config directory set");
        console.log("Specify a config directory with --cfgdir or -d");
        console.log("To build with no config (and no auto-update), pass the empty string (-d '')");
        return 1;
    }

    try {
        await fs.stat(path.join(WEBAPP_DIR, "index.html"));
    } catch {
        console.error(`${WEBAPP_DIR} is missing or incomplete. Build it first: pnpm --filter element-web build`);
        return 1;
    }

    // Stage a copy so the config override never modifies the web build output.
    const staging = await fs.mkdtemp(path.join(process.env.TMPDIR ?? "/tmp", "seventwos-webapp-"));
    try {
        await fs.cp(WEBAPP_DIR, staging, { recursive: true });
        if (cfgDir.length) {
            const source = path.join(cfgDir, "config.json");
            console.log(source + " -> config.json");
            await fs.copyFile(source, path.join(staging, "config.json"));
        } else {
            console.log("Skipping config file");
        }

        await fs.rm(ASAR_PATH, { force: true });
        console.log("Pack " + WEBAPP_DIR + " -> " + ASAR_PATH);
        await asar.createPackage(staging, ASAR_PATH);

        if (setVersion) {
            const semVer = (await fs.readFile(path.join(staging, "version"), "utf-8")).trim();
            console.log("Updating version to " + semVer);
            await setPackageVersion(semVer);
        }
    } finally {
        await fs.rm(staging, { recursive: true, force: true });
    }
    console.log("Done!");
}

main()
    .then((ret) => process.exit(ret))
    .catch((e) => {
        console.error(e);
        process.exit(1);
    });
