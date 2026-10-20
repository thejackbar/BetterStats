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
import { addPage, openDesign } from "@canva/design";
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
  featuredPhotoBlock,
  fieldBlock,
  lineUpBlock,
  matchDetailsBlock,
  MAX_LINEUP,
  PLAYER_EXTRAS,
  playerExtraBlock,
  sponsorsBlock,
} from "src/template/blocks";
import type { BlockSpec, PageSize } from "src/template/blocks";
import {
  ExportBlocked,
  exportTemplate,
  type ExportDeps,
  type ExportOutcome,
} from "src/template/exportFlow";
import type { PostType, TemplateFile } from "src/template/buildFile";
import { fetchImage } from "src/template/picture";
import { copyTemplate } from "src/template/saveFile";
import { insertBlock, type InsertResult } from "src/template/insert";
import { inCurrentPage } from "src/template/session";
import { bindFromToken, bindLabel } from "src/template/tokens";
import type { Surface } from "src/template/describe";
import type { Extraction, Skipped } from "src/template/types";

const lookupFonts: FontLookup = async (refs) => {
  const res = await findFonts({ fontRefs: refs as never });
  return res.fonts.map((f) => ({ ref: f.ref, name: f.name }));
};

// Shown as the club typed it, so it is data and not a translated message.
const tokenText = (token: string): string => `{{${token}}}`;

const exportDeps: ExportDeps = {
  inPage: inCurrentPage,
  fetchImage,
  lookupFonts,
};

type ExportView =
  | { status: "idle" }
  | { status: "working" }
  | { status: "blocked"; message: string; skipped: Skipped[] }
  | { status: "error"; message: string }
  | ({ status: "done" } & ExportOutcome);

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
  const [place, setPlace] = useState(1);
  const [extra, setExtra] = useState<string>("photo");
  const [placed, setPlaced] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice | undefined>(undefined);
  const [templateName, setTemplateName] = useState("Line up");
  const [postType, setPostType] = useState<PostType | undefined>(undefined);
  const [exp, setExp] = useState<ExportView>({ status: "idle" });

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

  // A new design is often 800 x 600, which is not a BetterCricket post shape. This adds a
  // square page (1080 x 1080) to build on instead.
  const addSquarePage = async () => {
    setBusy(true);
    setNotice(undefined);
    try {
      await addPage({ dimensions: { width: 1080, height: 1080 } });
      setNotice({
        tone: "positive",
        text: intl.formatMessage({
          defaultMessage:
            "A square page (1080 × 1080) was added at the end of the design. Open it, build your post there, and delete the old page if you do not need it.",
          description: "A square page was added to the design",
        }),
      });
    } catch (e) {
      setNotice({ tone: "critical", text: messageOf(e) });
    } finally {
      setBusy(false);
    }
  };

  const runExport = async () => {
    if (!postType) {
      return;
    }
    setBusy(true);
    setNotice(undefined);
    setExp({ status: "working" });
    try {
      const out = await exportTemplate(exportDeps, {
        name: templateName,
        postType,
      });
      setExp({ status: "done", ...out });
    } catch (e) {
      if (e instanceof ExportBlocked) {
        setExp({ status: "blocked", message: e.message, skipped: e.skipped });
      } else {
        setExp({ status: "error", message: messageOf(e) });
      }
    } finally {
      setBusy(false);
    }
  };

  const copyOut = async (file: TemplateFile) => {
    const ok = await copyTemplate(file);
    setNotice(
      ok
        ? {
            tone: "positive",
            text: intl.formatMessage({
              defaultMessage:
                "Template text copied. In BetterCricket, open BetterPosts, then paste it into “Import pasted text”. A line up goes into the Lineup design, anything else into the Blank canvas.",
              description: "After the template text was copied",
            }),
          }
        : {
            tone: "warn",
            text: intl.formatMessage({
              defaultMessage:
                "Your browser would not allow copying from here. Try again, or try a different browser.",
              description: "The copy was refused",
            }),
          },
    );
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
      rotated_group: intl.formatMessage(
        {
          defaultMessage:
            "“{text}” is in a rotated group. Rotate the group back to level.",
          description: "A token text box is inside a rotated group",
        },
        { text: s.text },
      ),
    })[s.reason];

  const surfaceText = (sf: Surface): string => {
    const kind = intl.formatMessage(
      {
        defaultMessage:
          "{kind, select, rect {Rectangle} shape {Shape} other {Other element}}",
        description: "Kind of a non-text element on the page",
      },
      { kind: sf.kind },
    );
    const fill = intl.formatMessage(
      {
        defaultMessage:
          "{fill, select, solid {solid {color}} image {a picture} video {a video} mixed {several fills} other {no fill}}",
        description: "What fills a non-text element on the page",
      },
      {
        fill: sf.fill.kind,
        color: sf.fill.kind === "solid" ? sf.fill.color : "",
      },
    );
    const line = intl.formatMessage(
      {
        defaultMessage: "{kind} {w} × {h} at {x}, {y}: {fill}",
        description: "One line describing a non-text element on the page",
      },
      { kind, fill, w: sf.w, h: sf.h, x: sf.x, y: sf.y },
    );
    const use = intl.formatMessage(
      {
        defaultMessage:
          "{use, select, panel {a panel behind your text} background {the background} area {the photo or sponsors area} other {left out}}",
        description: "What the export does with a non-text element",
      },
      { use: sf.use },
    );
    const turned = sf.rotation
      ? intl.formatMessage(
          {
            defaultMessage: ", turned {degrees}°",
            description: "Added to a line when the element is rotated",
          },
          { degrees: sf.rotation },
        )
      : "";
    return `${line}${turned} (${use})`;
  };

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

        <Button
          variant="secondary"
          onClick={addSquarePage}
          loading={busy}
          disabled={off}
          stretch
        >
          {intl.formatMessage({
            defaultMessage: "Start on a square page",
            description:
              "Button that adds a 1080 by 1080 page, a BetterCricket post shape",
          })}
        </Button>
        <FormField
          label={intl.formatMessage({
            defaultMessage: "What kind of post is this?",
            description: "Label for choosing the kind of post being made",
          })}
          description={intl.formatMessage({
            defaultMessage:
              "A line up goes into the Lineup design in BetterPosts, so the players you pick fill it in. Anything else goes onto the Blank canvas.",
            description: "Explains why the kind of post is asked for",
          })}
          control={(props) => (
            <Select
              {...props}
              options={[
                {
                  value: "lineup",
                  label: intl.formatMessage({
                    defaultMessage: "Line up",
                    description: "A kind of post: the team line up",
                  }),
                },
                {
                  value: "general",
                  label: intl.formatMessage({
                    defaultMessage: "Other post",
                    description:
                      "A kind of post: anything that is not a line up",
                  }),
                },
              ]}
              value={postType}
              placeholder={intl.formatMessage({
                defaultMessage: "Choose one",
                description: "Placeholder before a kind of post is chosen",
              })}
              onChange={(v) => setPostType(v as PostType)}
              stretch
            />
          )}
        />

        <Title size="xsmall">
          {intl.formatMessage({
            defaultMessage: "Add to this design",
            description: "Heading of the section that adds ready-made blocks",
          })}
        </Title>
        {postType !== "general" && (
          <Rows spacing="1u">
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
          </Rows>
        )}
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
        <Title size="xsmall">
          {intl.formatMessage({
            defaultMessage: "Add a player's photo or mark",
            description:
              "Heading of the section that adds a photo area or a captain, keeper or debut mark",
          })}
        </Title>
        <Text size="small">
          {intl.formatMessage({
            defaultMessage:
              "Captain, vice-captain, keeper and debut marks, C, VC, WK and DEBUT, are added after the names automatically, so you do not need boxes for them. Add a mark box only to place one yourself. A photo area is filled with that player's picture.",
            description: "Explains photos and marks",
          })}
        </Text>
        <FormField
          label={intl.formatMessage({
            defaultMessage: "Player place",
            description: "Label for which player place a photo or mark is for",
          })}
          control={(props) => (
            <NumberInput
              {...props}
              value={place}
              min={1}
              max={MAX_LINEUP}
              hasSpinButtons
              decrementAriaLabel={intl.formatMessage({
                defaultMessage: "One place earlier",
                description: "Accessible label for the minus button",
              })}
              incrementAriaLabel={intl.formatMessage({
                defaultMessage: "One place later",
                description: "Accessible label for the plus button",
              })}
              onChange={(value) => {
                if (value !== undefined) {
                  setPlace(value);
                }
              }}
            />
          )}
        />
        <FormField
          label={intl.formatMessage({
            defaultMessage: "What to add",
            description: "Label for choosing a photo or a mark",
          })}
          control={(props) => (
            <Select
              {...props}
              options={PLAYER_EXTRAS.map((e) => ({
                value: e,
                label: intl.formatMessage(
                  {
                    defaultMessage:
                      "{kind, select, photo {Photo area} captain {Captain mark} keeper {Keeper mark} debut {Debut mark} other {Vice-captain mark}}",
                    description: "A photo area or a mark a player can carry",
                  },
                  { kind: e === "vice captain" ? "vice" : e },
                ),
              }))}
              value={extra}
              onChange={setExtra}
              stretch
            />
          )}
        />
        <Button
          variant="secondary"
          onClick={async () => {
            const slot = placed;
            setPlaced((n) => n + 1);
            await addBlock((size) =>
              playerExtraBlock(size, place, extra, slot),
            );
          }}
          loading={busy}
          disabled={off}
          stretch
        >
          {intl.formatMessage({
            defaultMessage: "Add to player",
            description: "Button that adds a photo area or a mark for a player",
          })}
        </Button>
        <Button
          variant="secondary"
          onClick={() => addBlock((size) => featuredPhotoBlock(size))}
          loading={busy}
          disabled={off}
          stretch
        >
          {intl.formatMessage({
            defaultMessage: "Add featured photo",
            description:
              "Button that adds the photo area BetterPosts fills from its photo settings",
          })}
        </Button>
        <Button
          variant="secondary"
          onClick={() => addBlock((size) => sponsorsBlock(size))}
          loading={busy}
          disabled={off}
          stretch
        >
          {intl.formatMessage({
            defaultMessage: "Add sponsors box",
            description: "Button that adds a sponsors area to the design",
          })}
        </Button>
        <Text size="small" tone="tertiary">
          {intl.formatMessage({
            defaultMessage:
              "The grey rectangle only marks the area. Resize it and BetterCricket uses its size and place.",
            description: "Explains the grey marker rectangles",
          })}
        </Text>
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
            {state.result.surfaces.length > 0 && (
              <Rows spacing="0.5u">
                <Text size="small" tone="tertiary">
                  {intl.formatMessage({
                    defaultMessage: "Other things on this page",
                    description:
                      "Heading above the list of shapes and pictures on the page",
                  })}
                </Text>
                {state.result.surfaces.slice(0, 20).map((sf, i) => (
                  <Text key={`${sf.kind}-${i}`} size="small">
                    {surfaceText(sf)}
                  </Text>
                ))}
              </Rows>
            )}
            {state.result.skipped.map((s, i) => (
              <Alert key={`${s.text}-${i}`} tone="warn">
                {skippedText(s)}
              </Alert>
            ))}
            {!state.result.postSize && (
              <Button
                variant="secondary"
                onClick={addSquarePage}
                disabled={off}
                stretch
              >
                {intl.formatMessage({
                  defaultMessage: "Add a square page to build on",
                  description:
                    "Button shown when the page is not a BetterCricket post shape",
                })}
              </Button>
            )}
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
          {intl.formatMessage({
            defaultMessage:
              "Makes a template with the layout: where each field and fixed word sits, how big it is, the panels behind your words, and which colour and font each uses. Your background picture and any picture a panel is made from come across as pictures. BetterCricket fills in the club's own colours and fonts.",
            description: "Explains the export",
          })}
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
          disabled={off || !postType}
          stretch
          tooltipLabel={
            !postType
              ? intl.formatMessage({
                  defaultMessage: "Choose the kind of post first",
                  description: "Tooltip while no kind of post is chosen",
                })
              : undefined
          }
        >
          {intl.formatMessage({
            defaultMessage: "Export for BetterCricket",
            description: "Button that exports the template",
          })}
        </Button>
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
                  defaultMessage: "Template ready: {parts}.",
                  description: "The export finished",
                },
                {
                  parts: intl.formatList(
                    [
                      intl.formatMessage(
                        {
                          defaultMessage:
                            "{count, plural, one {# field} other {# fields}}",
                          description: "A number of fields",
                        },
                        { count: exp.fieldCount },
                      ),
                      intl.formatMessage(
                        {
                          defaultMessage:
                            "{count, plural, one {# fixed word} other {# fixed words}}",
                          description: "A number of fixed words",
                        },
                        { count: exp.textCount },
                      ),
                      ...(exp.panelCount
                        ? [
                            intl.formatMessage(
                              {
                                defaultMessage:
                                  "{count, plural, one {# panel} other {# panels}}",
                                description: "A number of panels",
                              },
                              { count: exp.panelCount },
                            ),
                          ]
                        : []),
                    ],
                    { type: "conjunction" },
                  ),
                },
              )}
            </Alert>
            {(exp.background || exp.panelPictures > 0) && (
              <Alert tone="positive">
                {intl.formatMessage(
                  {
                    defaultMessage: "Pictures included: {parts}.",
                    description:
                      "Which of the design's pictures are in the file",
                  },
                  {
                    parts: intl.formatList(
                      [
                        ...(exp.background
                          ? [
                              intl.formatMessage({
                                defaultMessage: "the background",
                                description:
                                  "The background picture is included",
                              }),
                            ]
                          : []),
                        ...(exp.panelPictures
                          ? [
                              intl.formatMessage(
                                {
                                  defaultMessage:
                                    "{count, plural, one {# panel picture} other {# panel pictures}}",
                                  description: "Panel pictures are included",
                                },
                                { count: exp.panelPictures },
                              ),
                            ]
                          : []),
                      ],
                      { type: "conjunction" },
                    ),
                  },
                )}
              </Alert>
            )}
            {exp.pictureProblems.map((problem, i) => (
              <Alert key={`${problem}-${i}`} tone="warn">
                {intl.formatMessage(
                  {
                    defaultMessage:
                      "A picture was left out. {problem} BetterCricket will draw a plain panel or its own background there.",
                    description: "A picture could not be brought across",
                  },
                  { problem },
                )}
              </Alert>
            ))}
            {exp.skipped.map((sk, i) => (
              <Alert key={`${sk.text}-${i}`} tone="warn">
                {skippedText(sk)}
              </Alert>
            ))}
            <Button variant="primary" onClick={() => copyOut(exp.file)} stretch>
              {intl.formatMessage({
                defaultMessage: "Copy template text",
                description: "Button that copies the template text",
              })}
            </Button>
          </Rows>
        )}
      </Rows>
    </div>
  );
};
