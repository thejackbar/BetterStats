import { useFeatureSupport } from "@canva/app-hooks";
import {
  Alert,
  Badge,
  Button,
  FormField,
  NumberInput,
  Rows,
  Select,
  Switch,
  Text,
  TextInput,
  Title,
} from "@canva/app-ui-kit";
import { findFonts } from "@canva/asset";
import { requestOpenExternalUrl } from "@canva/platform";
import { openDesign, requestExport } from "@canva/design";
import type { DesignEditing } from "@canva/design";
import { useState } from "react";
import { useIntl } from "react-intl";
import * as styles from "styles/components.css";
import {
  extractFields,
  isError,
  nameFonts,
  type ExtractError,
  type FontLookup,
} from "src/template/extract";
import {
  FIELD_TOKENS,
  fieldBlock,
  lineUpBlock,
  matchDetailsBlock,
  MAX_LINEUP,
} from "src/template/blocks";
import type { BlockSpec, PageSize } from "src/template/blocks";
import {
  ExportBlocked,
  PICTURE_LIMIT_BYTES,
  RestoreFailed,
  exportTemplate,
  restoreHidden,
  type ExportDeps,
} from "src/template/exportFlow";
import type { TemplateFile } from "src/template/buildFile";
import type { Hidden } from "src/template/hide";
import { fetchPicture } from "src/template/picture";
import { copyTemplate, downloadTemplate } from "src/template/saveFile";
import { insertBlock, type InsertResult } from "src/template/insert";
import { inCurrentPage } from "src/template/session";
import { bindFromToken, bindLabel } from "src/template/tokens";
import type { Extraction, Skipped } from "src/template/types";

const lookupFonts: FontLookup = async (refs) => {
  const res = await findFonts({ fontRefs: refs as never });
  return res.fonts.map((f) => ({ ref: f.ref, name: f.name }));
};

// Shown as the club typed it, so it is data and not a translated message.
const tokenText = (token: string): string => `{{${token}}}`;

const exportDeps: ExportDeps = {
  inPage: inCurrentPage,
  requestExport,
  fetchPicture,
  lookupFonts,
};

type ExportView =
  | { status: "idle" }
  | { status: "working" }
  | { status: "aborted" }
  | { status: "blocked"; message: string; skipped: Skipped[] }
  | { status: "error"; message: string }
  | { status: "done"; file: TemplateFile; fieldCount: number; bytes: number }
  | {
      status: "no_picture";
      file: TemplateFile;
      fieldCount: number;
      reason: string;
      url: string | null;
    };

const fieldOptions = FIELD_TOKENS.map((t) => ({
  value: t,
  label: bindLabel(bindFromToken(t) ?? t),
}));

type State =
  | { status: "idle" }
  | { status: "error"; message: string }
  | { status: "done"; result: Extraction };

type Notice = { tone: "positive" | "warn" | "critical"; text: string };

export const App = () => {
  const intl = useIntl();
  const isSupported = useFeatureSupport();
  const canRead = isSupported(openDesign);
  const [state, setState] = useState<State>({ status: "idle" });
  const [count, setCount] = useState(11);
  const [groupIt, setGroupIt] = useState(false);
  const [field, setField] = useState("player 1");
  const [placed, setPlaced] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice | undefined>(undefined);
  const [templateName, setTemplateName] = useState("Line up");
  const [exp, setExp] = useState<ExportView>({ status: "idle" });
  const [stuck, setStuck] = useState<Hidden[] | null>(null);

  const readPage = (
    session: DesignEditing.CurrentPageSession,
  ): Extraction | ExtractError =>
    session.page.type === "absolute"
      ? extractFields(session.page)
      : {
          error: intl.formatMessage({
            defaultMessage:
              "This kind of page cannot be read by apps. Use a normal design page, such as an Instagram post.",
            description: "Error when the open page is not a supported type",
          }),
        };

  // Names the fonts and shows the result. The page itself was copied out of the
  // Canva session already, so this can happen after the session has ended.
  const show = async (read: Extraction | ExtractError | undefined) => {
    if (!read) {
      setState({
        status: "error",
        message: intl.formatMessage({
          defaultMessage: "Canva did not give the app the page. Try again.",
          description: "Error when reading the page returned nothing",
        }),
      });
    } else if (isError(read)) {
      setState({ status: "error", message: read.error });
    } else {
      setState({ status: "done", result: await nameFonts(read, lookupFonts) });
    }
  };

  const messageOf = (e: unknown): string =>
    e instanceof Error && e.message
      ? e.message
      : intl.formatMessage({
          defaultMessage: "Something went wrong talking to Canva.",
          description: "Generic error when a Canva call failed",
        });

  const check = async () => {
    setBusy(true);
    setNotice(undefined);
    try {
      const out: { read?: Extraction | ExtractError } = {};
      await inCurrentPage(async (session) => {
        out.read = readPage(session);
      });
      await show(out.read);
    } catch (e) {
      setState({ status: "error", message: messageOf(e) });
    } finally {
      setBusy(false);
    }
  };

  // Adds boxes to the open page and re-reads the page in the SAME session, because
  // Canva allows only one session at a time.
  const addBlock = async (make: (size: PageSize) => BlockSpec) => {
    setBusy(true);
    setNotice(undefined);
    try {
      const out: {
        inserted?: InsertResult & { name: string };
        read?: Extraction | ExtractError;
      } = {};
      await inCurrentPage(async (session) => {
        const page = session.page;
        if (page.type !== "absolute" || !page.dimensions) {
          throw new Error(
            intl.formatMessage({
              defaultMessage:
                "This page has no fixed size, so a block cannot be laid out on it. Use a normal design page.",
              description: "Error when adding a block to a page without a size",
            }),
          );
        }
        const spec = make(page.dimensions);
        const r = await insertBlock(session, spec, { group: groupIt });
        out.inserted = { ...r, name: spec.name };
        out.read = readPage(session);
      });
      const done = out.inserted;
      if (done) {
        const values = { name: done.name, count: done.added };
        if (done.grouped) {
          setNotice({
            tone: "positive",
            text: intl.formatMessage(
              {
                defaultMessage:
                  "{name} added as one group. Move or resize it where you like.",
                description: "A block was added and grouped",
              },
              values,
            ),
          });
        } else if (done.groupError) {
          setNotice({
            tone: "warn",
            text: intl.formatMessage(
              {
                defaultMessage:
                  "{name} added, but Canva would not group the boxes ({reason}). They are loose on the page.",
                description: "A block was added but could not be grouped",
              },
              { ...values, reason: done.groupError },
            ),
          });
        } else {
          setNotice({
            tone: "positive",
            text: intl.formatMessage(
              {
                defaultMessage:
                  "{name} added: {count, plural, one {# text box} other {# separate text boxes}}. Move each one where you like.",
                description: "A block was added as separate text boxes",
              },
              values,
            ),
          });
        }
      }
      await show(out.read);
    } catch (e) {
      setNotice({ tone: "critical", text: messageOf(e) });
    } finally {
      setBusy(false);
    }
  };

  const runExport = async () => {
    setBusy(true);
    setNotice(undefined);
    setStuck(null);
    setExp({ status: "working" });
    try {
      const out = await exportTemplate(exportDeps, { name: templateName });
      if (out.status === "aborted") {
        setExp({ status: "aborted" });
      } else if (out.status === "done") {
        setExp({
          status: "done",
          file: out.file,
          fieldCount: out.fieldCount,
          bytes: out.pictureBytes,
        });
      } else {
        setExp({
          status: "no_picture",
          file: out.file,
          fieldCount: out.fieldCount,
          reason: out.reason,
          url: out.pictureUrl,
        });
      }
    } catch (e) {
      if (e instanceof RestoreFailed) {
        setStuck(e.hidden);
        setExp({ status: "error", message: e.message });
      } else if (e instanceof ExportBlocked) {
        setExp({ status: "blocked", message: e.message, skipped: e.skipped });
      } else {
        setExp({ status: "error", message: messageOf(e) });
      }
    } finally {
      setBusy(false);
    }
  };

  const restoreNow = async () => {
    if (!stuck) {
      return;
    }
    setBusy(true);
    try {
      await restoreHidden(inCurrentPage, stuck);
      setStuck(null);
      setExp({ status: "idle" });
      setNotice({
        tone: "positive",
        text: intl.formatMessage({
          defaultMessage: "Your text boxes are back.",
          description: "The hidden placeholder boxes were restored",
        }),
      });
    } catch (e) {
      setNotice({ tone: "critical", text: messageOf(e) });
    } finally {
      setBusy(false);
    }
  };

  const saveTemplate = (file: TemplateFile, how: "download" | "copy") => {
    const sent = how === "download" ? downloadTemplate(file) : null;
    const done = (ok: boolean) =>
      setNotice(
        ok
          ? {
              tone: "positive",
              text:
                how === "download"
                  ? intl.formatMessage({
                      defaultMessage:
                        "Template file saved. In BetterCricket, open BetterPosts, Blank canvas, and choose Import a template file.",
                      description: "After the template file was downloaded",
                    })
                  : intl.formatMessage({
                      defaultMessage:
                        "Template text copied. In BetterCricket, paste it into the Import box on the Blank canvas.",
                      description: "After the template text was copied",
                    }),
            }
          : {
              tone: "warn",
              text:
                how === "download"
                  ? intl.formatMessage({
                      defaultMessage:
                        "Your browser would not save the file from here. Use Copy template text instead.",
                      description: "The download was refused",
                    })
                  : intl.formatMessage({
                      defaultMessage:
                        "Your browser would not allow copying from here.",
                      description: "The copy was refused",
                    }),
            },
      );
    if (sent != null) {
      done(sent);
    } else {
      void copyTemplate(file).then(done);
    }
  };

  const skippedText = (s: Skipped): string =>
    ({
      mixed: intl.formatMessage(
        {
          defaultMessage:
            "“{text}” has other words with the token. Put each token in its own text box.",
          description: "A text box mixes a token with other words",
        },
        { text: s.text },
      ),
      locked: intl.formatMessage(
        {
          defaultMessage:
            "“{text}” is locked. Unlock it so it can be hidden when the picture is exported.",
          description: "A token text box is locked",
        },
        { text: s.text },
      ),
      rotated_group: intl.formatMessage(
        {
          defaultMessage:
            "“{text}” is in a rotated group. Rotate the group back to level.",
          description: "A token text box is inside a rotated group",
        },
        { text: s.text },
      ),
    })[s.reason];

  const off = !canRead || busy;

  return (
    <div className={styles.scrollContainer}>
      <Rows spacing="2u">
        <Title size="small">
          {intl.formatMessage({
            defaultMessage: "BetterCricket template",
            description: "Heading of the app panel",
          })}
        </Title>
        <Text size="small">
          {intl.formatMessage(
            {
              defaultMessage:
                "Add a block below, or type a field into its own text box, like {player}, {opponent} or {date}. BetterCricket fills it in with live club details. Use {caps} in capitals for capital letters.",
              description:
                "How to mark a field. The values are example fields and are not translated.",
            },
            {
              player: "{{player 1}}",
              opponent: "{{opponent}}",
              date: "{{date}}",
              caps: "{{PLAYER 1}}",
            },
          )}
        </Text>

        <Title size="xsmall">
          {intl.formatMessage({
            defaultMessage: "Add to this design",
            description: "Heading of the section that adds ready-made blocks",
          })}
        </Title>
        <FormField
          label={intl.formatMessage({
            defaultMessage: "Players in the line up",
            description: "Label for the number of player places to add",
          })}
          control={(props) => (
            <NumberInput
              {...props}
              value={count}
              min={1}
              max={MAX_LINEUP}
              hasSpinButtons
              decrementAriaLabel={intl.formatMessage({
                defaultMessage: "One fewer player",
                description: "Accessible label for the minus button",
              })}
              incrementAriaLabel={intl.formatMessage({
                defaultMessage: "One more player",
                description: "Accessible label for the plus button",
              })}
              onChange={(value) => {
                if (value !== undefined) {
                  setCount(value);
                }
              }}
            />
          )}
        />
        <Button
          variant="secondary"
          onClick={() => addBlock((size) => lineUpBlock(size, count))}
          loading={busy}
          disabled={off}
          stretch
        >
          {intl.formatMessage({
            defaultMessage: "Add line up",
            description: "Button that adds a line up block to the design",
          })}
        </Button>
        <Button
          variant="secondary"
          onClick={() => addBlock((size) => matchDetailsBlock(size))}
          loading={busy}
          disabled={off}
          stretch
        >
          {intl.formatMessage({
            defaultMessage: "Add match details",
            description: "Button that adds a match details block to the design",
          })}
        </Button>
        <Switch
          value={groupIt}
          onChange={setGroupIt}
          disabled={busy}
          label={intl.formatMessage({
            defaultMessage: "Group the boxes together",
            description: "Switch: put an added block's text boxes in one group",
          })}
          description={intl.formatMessage({
            defaultMessage:
              "Off gives you separate boxes to place one by one. On makes the block move as one.",
            description: "Explains the group switch",
          })}
        />

        <Title size="xsmall">
          {intl.formatMessage({
            defaultMessage: "Add one field",
            description: "Heading of the section that adds a single field",
          })}
        </Title>
        <FormField
          label={intl.formatMessage({
            defaultMessage: "Field",
            description: "Label for the choice of a single field to add",
          })}
          control={(props) => (
            <Select
              {...props}
              options={fieldOptions}
              value={field}
              onChange={setField}
              stretch
            />
          )}
        />
        <Button
          variant="secondary"
          onClick={async () => {
            const slot = placed;
            setPlaced((n) => n + 1);
            await addBlock((size) => fieldBlock(size, field, slot));
          }}
          loading={busy}
          disabled={off}
          stretch
        >
          {intl.formatMessage({
            defaultMessage: "Add field",
            description: "Button that adds one field's text box to the design",
          })}
        </Button>
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

        <Button
          variant="primary"
          onClick={check}
          loading={busy}
          disabled={off}
          stretch
          tooltipLabel={
            !canRead
              ? intl.formatMessage({
                  defaultMessage: "This page cannot be read here",
                  description: "Tooltip when reading the design is unsupported",
                })
              : undefined
          }
        >
          {intl.formatMessage({
            defaultMessage: "Check this page",
            description: "Button that reads the page for fields",
          })}
        </Button>

        {state.status === "error" && (
          <Alert tone="critical">{state.message}</Alert>
        )}

        {state.status === "done" && (
          <Rows spacing="1u">
            <Text size="small" tone="tertiary">
              {intl.formatMessage(
                {
                  defaultMessage:
                    "Post size {w} × {h}. {count, plural, =0 {No fields found.} one {# field found.} other {# fields found.}}",
                  description: "Summary after reading the page",
                },
                {
                  w: state.result.canvas.w,
                  h: state.result.canvas.h,
                  count: state.result.fields.length,
                },
              )}
            </Text>
            {state.result.fields.map((f, i) => (
              <Rows key={`${f.token}-${i}`} spacing="0.5u">
                <Text>{tokenText(f.token)}</Text>
                {f.binding ? (
                  <Badge tone="positive" text={bindLabel(f.binding)} />
                ) : (
                  <Badge
                    tone="warn"
                    text={intl.formatMessage({
                      defaultMessage: "Not a BetterCricket field",
                      description:
                        "Badge for a token BetterCricket does not know",
                    })}
                  />
                )}
              </Rows>
            ))}
            {state.result.fields.length === 0 &&
              state.result.skipped.length === 0 && (
                <Alert tone="info">
                  {intl.formatMessage(
                    {
                      defaultMessage:
                        "No fields on this page yet. Type {example} into a text box and check again.",
                      description:
                        "Nothing found on the page. The value is an example field.",
                    },
                    { example: "{{player 1}}" },
                  )}
                </Alert>
              )}
            {state.result.skipped.map((s, i) => (
              <Alert key={`${s.text}-${i}`} tone="warn">
                {skippedText(s)}
              </Alert>
            ))}
            {state.result.warnings.map((w, i) => (
              <Alert key={`${w}-${i}`} tone="warn">
                {w}
              </Alert>
            ))}
          </Rows>
        )}

        <Title size="xsmall">
          {intl.formatMessage({
            defaultMessage: "Export for BetterCricket",
            description: "Heading of the export section",
          })}
        </Title>
        <Text size="small">
          {intl.formatMessage(
            {
              defaultMessage:
                "Makes a template file with your design as the picture and a field for each {example}. Those words are hidden for a moment while the picture is made, then put back.",
              description:
                "Explains the export. The value is an example field, not translated.",
            },
            { example: "{{player 1}}" },
          )}
        </Text>
        <FormField
          label={intl.formatMessage({
            defaultMessage: "Template name",
            description: "Label for the name of the exported template",
          })}
          control={(props) => (
            <TextInput
              {...props}
              value={templateName}
              onChange={setTemplateName}
              disabled={busy}
            />
          )}
        />
        <Button
          variant="primary"
          onClick={runExport}
          loading={exp.status === "working"}
          disabled={off}
          stretch
        >
          {intl.formatMessage({
            defaultMessage: "Export for BetterCricket",
            description: "Button that exports the template",
          })}
        </Button>
        {stuck && (
          <Button
            variant="secondary"
            onClick={restoreNow}
            disabled={busy}
            stretch
          >
            {intl.formatMessage({
              defaultMessage: "Restore placeholders",
              description: "Button that puts hidden text boxes back",
            })}
          </Button>
        )}
        {exp.status === "aborted" && (
          <Alert tone="info">
            {intl.formatMessage({
              defaultMessage:
                "Export cancelled. Your text boxes are back as they were.",
              description: "The export dialog was closed",
            })}
          </Alert>
        )}
        {exp.status === "error" && <Alert tone="critical">{exp.message}</Alert>}
        {exp.status === "blocked" && (
          <Rows spacing="1u">
            <Alert tone="warn">{exp.message}</Alert>
            {exp.skipped.map((sk, i) => (
              <Alert key={`${sk.text}-${i}`} tone="warn">
                {skippedText(sk)}
              </Alert>
            ))}
          </Rows>
        )}
        {exp.status === "done" && (
          <Rows spacing="1u">
            <Alert tone="positive">
              {intl.formatMessage(
                {
                  defaultMessage:
                    "Template ready: {count, plural, one {# field} other {# fields}} and the picture ({size} MB).",
                  description: "The export finished",
                },
                {
                  count: exp.fieldCount,
                  size: (exp.bytes / 1024 / 1024).toFixed(1),
                },
              )}
            </Alert>
            {exp.bytes > PICTURE_LIMIT_BYTES && (
              <Alert tone="warn">
                {intl.formatMessage({
                  defaultMessage:
                    "BetterCricket takes pictures up to 5 MB, so it may refuse this one. Export again and choose JPG.",
                  description:
                    "The exported picture is over BetterCricket's limit",
                })}
              </Alert>
            )}
            <Button
              variant="secondary"
              onClick={() => saveTemplate(exp.file, "download")}
              stretch
            >
              {intl.formatMessage({
                defaultMessage: "Download template file",
                description: "Button that downloads the template file",
              })}
            </Button>
            <Button
              variant="secondary"
              onClick={() => saveTemplate(exp.file, "copy")}
              stretch
            >
              {intl.formatMessage({
                defaultMessage: "Copy template text",
                description: "Button that copies the template text",
              })}
            </Button>
          </Rows>
        )}
        {exp.status === "no_picture" && (
          <Rows spacing="1u">
            <Alert tone="warn">
              {intl.formatMessage(
                {
                  defaultMessage:
                    "The {count, plural, one {# field is} other {# fields are}} ready, but the picture could not be fetched ({reason}). You can still use the fields and upload the picture in BetterCricket under Your own design.",
                  description:
                    "The export worked but the picture could not be fetched",
                },
                { count: exp.fieldCount, reason: exp.reason },
              )}
            </Alert>
            {exp.url && (
              <Button
                variant="secondary"
                onClick={() => {
                  if (exp.url) {
                    void requestOpenExternalUrl({ url: exp.url });
                  }
                }}
                stretch
              >
                {intl.formatMessage({
                  defaultMessage: "Open the picture",
                  description: "Button that opens the exported picture",
                })}
              </Button>
            )}
            <Button
              variant="secondary"
              onClick={() => saveTemplate(exp.file, "download")}
              stretch
            >
              {intl.formatMessage({
                defaultMessage: "Download fields only",
                description:
                  "Button that downloads a template without its picture",
              })}
            </Button>
            <Button
              variant="secondary"
              onClick={() => saveTemplate(exp.file, "copy")}
              stretch
            >
              {intl.formatMessage({
                defaultMessage: "Copy fields only",
                description:
                  "Button that copies a template without its picture",
              })}
            </Button>
          </Rows>
        )}
      </Rows>
    </div>
  );
};
