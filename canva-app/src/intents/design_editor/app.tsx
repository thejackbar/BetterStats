import { useFeatureSupport } from "@canva/app-hooks";
import {
  Alert,
  Badge,
  Button,
  FormField,
  NumberInput,
  Rows,
  Text,
  Title,
} from "@canva/app-ui-kit";
import { findFonts } from "@canva/asset";
import { openDesign } from "@canva/design";
import { useState } from "react";
import { useIntl } from "react-intl";
import * as styles from "styles/components.css";
import {
  extractFields,
  isError,
  nameFonts,
  type FontLookup,
} from "src/template/extract";
import {
  lineUpBlock,
  matchDetailsBlock,
  MAX_LINEUP,
} from "src/template/blocks";
import type { BlockSpec, PageSize } from "src/template/blocks";
import { insertBlock } from "src/template/insert";
import { bindLabel } from "src/template/tokens";
import type { Extraction, Skipped } from "src/template/types";

const lookupFonts: FontLookup = async (refs) => {
  const res = await findFonts({ fontRefs: refs as never });
  return res.fonts.map((f) => ({ ref: f.ref, name: f.name }));
};

// Shown as the club typed it, so it is data and not a translated message.
const tokenText = (token: string): string => `{{${token}}}`;

type State =
  | { status: "idle" }
  | { status: "reading" }
  | { status: "error"; message: string }
  | { status: "done"; result: Extraction };

export const App = () => {
  const intl = useIntl();
  const isSupported = useFeatureSupport();
  const canRead = isSupported(openDesign);
  const [state, setState] = useState<State>({ status: "idle" });
  const [count, setCount] = useState(11);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<
    { tone: "positive" | "warn" | "critical"; text: string } | undefined
  >(undefined);

  // Adds a ready-made block of text boxes to the open page, then re-reads the page
  // so the field list shows what was added.
  const addBlock = async (make: (size: PageSize) => BlockSpec) => {
    setAdding(true);
    setNotice(undefined);
    try {
      let result: { added: number; grouped: boolean; name: string } | undefined;
      await openDesign({ type: "current_page" }, async (session) => {
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
        const r = await insertBlock(session, spec);
        result = { ...r, name: spec.name };
      });
      if (result) {
        const done = result;
        setNotice(
          done.grouped
            ? {
                tone: "positive",
                text: intl.formatMessage(
                  {
                    defaultMessage:
                      "{name} added to the page as one group. Move or resize it where you like.",
                    description: "A block was added and grouped",
                  },
                  { name: done.name },
                ),
              }
            : {
                tone: "warn",
                text: intl.formatMessage(
                  {
                    defaultMessage:
                      "{name} added, but Canva would not group the boxes. They are loose on the page.",
                    description: "A block was added but could not be grouped",
                  },
                  { name: done.name },
                ),
              },
        );
        await check();
      }
    } catch (e) {
      setNotice({
        tone: "critical",
        text:
          e instanceof Error && e.message
            ? e.message
            : intl.formatMessage({
                defaultMessage: "Something went wrong adding the block.",
                description: "Generic error when adding a block failed",
              }),
      });
    } finally {
      setAdding(false);
    }
  };

  const check = async () => {
    setState({ status: "reading" });
    try {
      // The session ends when this callback does, so everything needed is
      // copied out into plain data before it returns.
      const out: { value: ReturnType<typeof extractFields> | null } = {
        value: null,
      };
      await openDesign({ type: "current_page" }, async (session) => {
        if (session.page.type !== "absolute") {
          out.value = {
            error: intl.formatMessage({
              defaultMessage:
                "This kind of page cannot be read by apps. Use a normal design page, such as an Instagram post.",
              description: "Error when the open page is not a supported type",
            }),
          };
          return;
        }
        out.value = extractFields(session.page);
      });
      const read = out.value;
      if (!read) {
        setState({
          status: "error",
          message: intl.formatMessage({
            defaultMessage: "Canva did not give the app the page. Try again.",
            description: "Error when reading the page returned nothing",
          }),
        });
        return;
      }
      if (isError(read)) {
        setState({ status: "error", message: read.error });
        return;
      }
      setState({ status: "done", result: await nameFonts(read, lookupFonts) });
    } catch (e) {
      setState({
        status: "error",
        message:
          e instanceof Error && e.message
            ? e.message
            : intl.formatMessage({
                defaultMessage: "Something went wrong reading the page.",
                description: "Generic error when reading the page failed",
              }),
      });
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
          loading={adding}
          disabled={!canRead || adding}
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
          loading={adding}
          disabled={!canRead || adding}
          stretch
        >
          {intl.formatMessage({
            defaultMessage: "Add match details",
            description: "Button that adds a match details block to the design",
          })}
        </Button>
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

        <Button
          variant="primary"
          onClick={check}
          loading={state.status === "reading"}
          disabled={!canRead}
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
      </Rows>
    </div>
  );
};
