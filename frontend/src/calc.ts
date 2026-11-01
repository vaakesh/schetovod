// an exact fraction, 0.1 * 3 stays 0.3 where a float would not
interface Fraction {
  top: bigint;
  bottom: bigint;
}

const OPERATOR = /[-+*/×÷:хx−–()]/i;

// the signs a keyboard may give for the same operation
function normalize(input: string): string {
  return input
    .replace(/\s/g, "")
    .replace(/[×хx]/gi, "*")
    .replace(/[÷:]/g, "/")
    .replace(/[−–]/g, "-");
}

function multiply(a: Fraction, b: Fraction): Fraction {
  return { top: a.top * b.top, bottom: a.bottom * b.bottom };
}

function add(a: Fraction, b: Fraction): Fraction {
  return { top: a.top * b.bottom + b.top * a.bottom, bottom: a.bottom * b.bottom };
}

function negate(a: Fraction): Fraction {
  return { top: -a.top, bottom: a.bottom };
}

// a recursive descent, the failed parse of a broken expression is thrown and caught once
class Parser {
  private position = 0;

  constructor(private readonly text: string) {}

  parse(): Fraction {
    const result = this.sum();
    if (this.position !== this.text.length) {
      throw new Error("unexpected character");
    }
    return result;
  }

  private peek(): string | undefined {
    return this.text[this.position];
  }

  private sum(): Fraction {
    let result = this.product();
    for (let sign = this.peek(); sign === "+" || sign === "-"; sign = this.peek()) {
      this.position += 1;
      const next = this.product();
      result = add(result, sign === "+" ? next : negate(next));
    }
    return result;
  }

  private product(): Fraction {
    let result = this.factor();
    for (let sign = this.peek(); sign === "*" || sign === "/"; sign = this.peek()) {
      this.position += 1;
      const next = this.factor();
      if (sign === "/" && next.top === BigInt(0)) {
        throw new Error("division by zero");
      }
      result = multiply(result, sign === "*" ? next : { top: next.bottom, bottom: next.top });
    }
    return result;
  }

  private factor(): Fraction {
    const sign = this.peek();
    if (sign === "-" || sign === "+") {
      this.position += 1;
      const next = this.factor();
      return sign === "-" ? negate(next) : next;
    }
    if (sign === "(") {
      this.position += 1;
      const inner = this.sum();
      if (this.peek() !== ")") {
        throw new Error("unclosed bracket");
      }
      this.position += 1;
      return inner;
    }
    return this.number();
  }

  private number(): Fraction {
    const match = /^(\d*)[.,]?(\d*)/.exec(this.text.slice(this.position));
    const whole = match?.[1] ?? "";
    const part = match?.[2] ?? "";
    if (whole === "" && part === "") {
      throw new Error("a number is expected");
    }
    this.position += match?.[0].length ?? 0;
    return {
      top: BigInt(`${whole}${part}`),
      bottom: BigInt(10) ** BigInt(part.length),
    };
  }
}

// kopecks rounded half up, without the trailing zeros
function toMoney({ top, bottom }: Fraction): string {
  const hundred = BigInt(100);
  const two = BigInt(2);
  const negative = top < BigInt(0) !== bottom < BigInt(0);
  const above = top < BigInt(0) ? -top : top;
  const below = bottom < BigInt(0) ? -bottom : bottom;
  const kopecks = (two * above * hundred + below) / (two * below);
  const part = String(kopecks % hundred)
    .padStart(2, "0")
    .replace(/0+$/, "");
  const whole = String(kopecks / hundred);
  const sign = negative && kopecks !== BigInt(0) ? "-" : "";
  return part === "" ? `${sign}${whole}` : `${sign}${whole}.${part}`;
}

// the sum of an expression as the api takes it, null when it can not be counted
export function calculate(input: string): string | null {
  try {
    return toMoney(new Parser(normalize(input)).parse());
  } catch {
    return null;
  }
}

export function isExpression(input: string): boolean {
  return OPERATOR.test(input);
}
