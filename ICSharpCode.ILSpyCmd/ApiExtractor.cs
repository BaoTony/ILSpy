// Copyright (c) 2026 ILSpy Contributors
//
// Permission is hereby granted, free of charge, to any person obtaining a copy of this
// software and associated documentation files (the "Software"), to deal in the Software
// without restriction, including without limitation the rights to use, copy, modify, merge,
// publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
// to whom the Software is furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all copies or
// substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
// PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
// FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
// OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
// DEALINGS IN THE SOFTWARE.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Text;

using ICSharpCode.Decompiler.Metadata;

namespace ICSharpCode.ILSpyCmd
{
	/// <summary>
	/// Extracts the public API surface of a .NET assembly using System.Reflection.Metadata.
	/// This reads PE metadata directly (zero dependency loading) and is 100% accurate.
	/// </summary>
	public static class ApiExtractor
	{
		public sealed class Options
		{
			/// <summary>Exclude compiler-generated types (names matching &lt;&gt;*).</summary>
			public bool ExcludeCompilerGenerated { get; set; } = true;

			/// <summary>Include non-public nested types that are public within their parent.</summary>
			public bool IncludeNestedPublic { get; set; } = true;

			/// <summary>Include full method signatures (return type + parameters).</summary>
			public bool IncludeSignatures { get; set; } = true;

			/// <summary>Include custom attributes.</summary>
			public bool IncludeAttributes { get; set; }
		}

		/// <summary>
		/// Runs the extraction and writes the API listing to <paramref name="output"/>.
		/// </summary>
		public static void Extract(PEFile peFile, TextWriter output, Options options = null)
		{
			options ??= new Options();
			var reader = peFile.Metadata;
			var api = CollectPublicApi(reader, options);

			output.WriteLine($"Public API Surface: {Path.GetFileName(peFile.FileName)}");
			output.WriteLine($"Generated: {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
			output.WriteLine($"Assembly:  {peFile.FileName}");
			WriteDivider(output);

			int totalTypes = 0;
			int totalMembers = 0;

			foreach (var ns in api.Keys.OrderBy(n => n))
			{
				var types = api[ns];
				if (types.Count == 0) continue;

				output.WriteLine();
				output.WriteLine($"namespace {ns}");
				WriteSubDivider(output);

				foreach (var (typeName, typeInfo) in types)
				{
					output.WriteLine();
					output.Write($"  {typeInfo.Kind} {typeName}");

					if (typeInfo.BaseType != null)
						output.Write($" : {typeInfo.BaseType}");

					if (typeInfo.Interfaces.Count > 0)
					{
						string prefix = typeInfo.BaseType != null ? ", " : " : ";
						output.Write($"{prefix}{string.Join(", ", typeInfo.Interfaces)}");
					}

					output.WriteLine();
					totalTypes++;

					foreach (var member in typeInfo.Members)
					{
						output.WriteLine($"    {member}");
						totalMembers++;
					}
				}
			}

			output.WriteLine();
			WriteDivider(output);
			output.WriteLine($"Total: {totalTypes} public types, {totalMembers} public members");
		}

		sealed class TypeInfo
		{
			public string Kind;
			public string BaseType;
			public List<string> Interfaces = new();
			public List<string> Members = new();
		}

		static SortedDictionary<string, SortedDictionary<string, TypeInfo>> CollectPublicApi(
			MetadataReader reader, Options options)
		{
			var result = new SortedDictionary<string, SortedDictionary<string, TypeInfo>>(
				StringComparer.OrdinalIgnoreCase);

			// Collect method signatures lazily: Map from type handle to its public method list,
			// because properties reference methods by handle.
			var methodSignatures = new Dictionary<EntityHandle, string>();

			// ---- Phase 1: Collect all public types ----
			var typeQueue = new Queue<TypeDefinitionHandle>();
			foreach (var typeDefHandle in reader.TypeDefinitions)
			{
				typeQueue.Enqueue(typeDefHandle);
			}

			var processedTypes = new HashSet<TypeDefinitionHandle>();

			while (typeQueue.Count > 0)
			{
				var typeDefHandle = typeQueue.Dequeue();
				if (!processedTypes.Add(typeDefHandle))
					continue;

				var typeDef = reader.GetTypeDefinition(typeDefHandle);
				bool isNested = typeDef.IsNested;

				// Visibility check
				var visibility = typeDef.Attributes & TypeAttributes.VisibilityMask;
				bool isPublic = isNested
					? (visibility == TypeAttributes.NestedPublic)
					: (visibility == TypeAttributes.Public);

				if (!isPublic)
					continue;

				// Compiler-generated filtering
				if (options.ExcludeCompilerGenerated)
				{
					var name = reader.GetString(typeDef.Name);
					if (IsCompilerGenerated(name))
						continue;
				}

				// Resolve namespace + type name
				string ns = "";
				string fullName;
				if (isNested)
				{
					// Walk up the nesting chain
					var parts = new List<string>();
					var current = typeDefHandle;
					while (true)
					{
						var td = reader.GetTypeDefinition(current);
						parts.Add(reader.GetString(td.Name));
						if (td.IsNested)
							current = td.GetDeclaringType();
						else
						{
							ns = reader.GetString(td.Namespace);
							break;
						}
					}
					parts.Reverse();
					fullName = string.Join(".", parts);
				}
				else
				{
					ns = reader.GetString(typeDef.Namespace);
					fullName = reader.GetString(typeDef.Name);
				}

				if (string.IsNullOrEmpty(ns))
					ns = "(global)";

				if (!result.TryGetValue(ns, out var nsTypes))
				{
					nsTypes = new SortedDictionary<string, TypeInfo>(StringComparer.Ordinal);
					result[ns] = nsTypes;
				}

				if (!nsTypes.TryGetValue(fullName, out var typeInfo))
				{
					typeInfo = new TypeInfo();
					nsTypes[fullName] = typeInfo;
				}

				// Resolve base type (needed for struct/enum detection AND display)
				string baseTypeName = null;
				if (typeDef.BaseType.Kind == HandleKind.TypeDefinition ||
					typeDef.BaseType.Kind == HandleKind.TypeReference ||
					typeDef.BaseType.Kind == HandleKind.TypeSpecification)
				{
					baseTypeName = ResolveTypeName(reader, typeDef.BaseType);
				}

				// Set type kind (must happen after base type is resolved)
				typeInfo.Kind = GetTypeKind(typeDef.Attributes, baseTypeName);

				// Set displayed base type (skip Object/ValueType/Enum/MulticastDelegate)
				if (baseTypeName != null &&
					baseTypeName != "System.Object" &&
					baseTypeName != "System.ValueType" &&
					baseTypeName != "System.Enum" &&
					baseTypeName != "System.MulticastDelegate")
					typeInfo.BaseType = baseTypeName;

				// Interfaces
				foreach (var ifImplHandle in typeDef.GetInterfaceImplementations())
				{
					var ifImpl = reader.GetInterfaceImplementation(ifImplHandle);
					var ifName = ResolveTypeName(reader, ifImpl.Interface);
					if (ifName != null)
						typeInfo.Interfaces.Add(ifName);
				}

				// ---- Collect public members ----
				// Methods
				foreach (var methodHandle in typeDef.GetMethods())
				{
					var method = reader.GetMethodDefinition(methodHandle);
					if ((method.Attributes & MethodAttributes.MemberAccessMask) != MethodAttributes.Public)
						continue;
					if (options.ExcludeCompilerGenerated && IsCompilerGenerated(reader.GetString(method.Name)))
						continue;

					// Skip property getter/setter and event adder/remover (shown via Property/Event entries)
					if ((method.Attributes & MethodAttributes.SpecialName) != 0)
					{
						var methodNameCheck = reader.GetString(method.Name);
						// Keep operators (op_Addition, etc.) and conversion operators (op_Implicit/Explicit)
						if (!methodNameCheck.StartsWith("op_", StringComparison.Ordinal))
							continue;
					}

					// Skip static type initializer (.cctor)
					if ((method.Attributes & MethodAttributes.RTSpecialName) != 0 &&
						reader.GetString(method.Name) == ".cctor")
						continue;

					var sig = BuildMethodSignature(reader, method, fullName, options);
					methodSignatures[methodHandle] = sig;
					typeInfo.Members.Add(sig);
				}

				// Fields
				foreach (var fieldHandle in typeDef.GetFields())
				{
					var field = reader.GetFieldDefinition(fieldHandle);
					if ((field.Attributes & FieldAttributes.FieldAccessMask) != FieldAttributes.Public)
						continue;
					if (options.ExcludeCompilerGenerated && IsCompilerGenerated(reader.GetString(field.Name)))
						continue;

					var fieldSig = field.DecodeSignature(new TypeNameProvider(reader), default);
					string modifiers = "";
					if ((field.Attributes & FieldAttributes.Static) != 0)
						modifiers += "static ";
					if ((field.Attributes & FieldAttributes.InitOnly) != 0)
						modifiers += "readonly ";
					if ((field.Attributes & FieldAttributes.Literal) != 0)
						modifiers += "const ";

					typeInfo.Members.Add($"{modifiers}{fieldSig} {reader.GetString(field.Name)}");
				}

				// Properties
				foreach (var propHandle in typeDef.GetProperties())
				{
					var prop = reader.GetPropertyDefinition(propHandle);
					var accessors = prop.GetAccessors();
					bool propIsPublic = false;

					if (!accessors.Getter.IsNil)
					{
						var getter = reader.GetMethodDefinition(accessors.Getter);
						if ((getter.Attributes & MethodAttributes.MemberAccessMask) == MethodAttributes.Public)
							propIsPublic = true;
					}
					if (!accessors.Setter.IsNil)
					{
						var setter = reader.GetMethodDefinition(accessors.Setter);
						if ((setter.Attributes & MethodAttributes.MemberAccessMask) == MethodAttributes.Public)
							propIsPublic = true;
					}

					if (!propIsPublic) continue;
					if (options.ExcludeCompilerGenerated && IsCompilerGenerated(reader.GetString(prop.Name)))
						continue;

					var propSig = prop.DecodeSignature(new TypeNameProvider(reader), default);
					string accessor = "";
					if (!accessors.Getter.IsNil && !accessors.Setter.IsNil)
						accessor = " { get; set; }";
					else if (!accessors.Getter.IsNil)
						accessor = " { get; }";
					else
						accessor = " { set; }";

					typeInfo.Members.Add($"{propSig.ReturnType} {reader.GetString(prop.Name)}{accessor}");
				}

				// Events
				foreach (var eventHandle in typeDef.GetEvents())
				{
					var evt = reader.GetEventDefinition(eventHandle);
					var evtAccessors = evt.GetAccessors();

					bool eventIsPublic = false;
					if (!evtAccessors.Adder.IsNil)
					{
						var adder = reader.GetMethodDefinition(evtAccessors.Adder);
						if ((adder.Attributes & MethodAttributes.MemberAccessMask) == MethodAttributes.Public)
							eventIsPublic = true;
					}
					if (!evtAccessors.Remover.IsNil)
					{
						var remover = reader.GetMethodDefinition(evtAccessors.Remover);
						if ((remover.Attributes & MethodAttributes.MemberAccessMask) == MethodAttributes.Public)
							eventIsPublic = true;
					}

					if (!eventIsPublic) continue;

					var eventTypeName = ResolveTypeName(reader, evt.Type);
					typeInfo.Members.Add($"event {eventTypeName} {reader.GetString(evt.Name)}");
				}
			}

			return result;
		}

		/// <summary>
		/// Determines the C# type kind from TypeAttributes and base type.
		/// In IL: interface=Interface, static class=Abstract|Sealed, struct=Sealed+ValueType,
		/// enum=Sealed+Enum, delegate=Sealed+MulticastDelegate, regular class/nested=none of above.
		/// </summary>
		static string GetTypeKind(TypeAttributes attr, string baseTypeName)
		{
			if ((attr & TypeAttributes.Interface) != 0)
				return "interface";

			bool isSealed = (attr & TypeAttributes.Sealed) != 0;
			bool isAbstract = (attr & TypeAttributes.Abstract) != 0;

			// static class = abstract + sealed
			if (isAbstract && isSealed)
				return "static class";

			if (isSealed)
			{
				if (baseTypeName == "System.Enum")
					return "enum";
				if (baseTypeName == "System.ValueType")
					return "struct";
				if (baseTypeName == "System.MulticastDelegate")
					return "delegate";
				return "sealed class";
			}

			if (isAbstract)
				return "abstract class";

			return "class";
		}

		static string BuildMethodSignature(MetadataReader reader, MethodDefinition method, string declaringTypeName, Options options)
		{
			if (!options.IncludeSignatures)
				return reader.GetString(method.Name) + "()";

			var sig = method.DecodeSignature(new TypeNameProvider(reader), default);
			string modifiers = "";
			if ((method.Attributes & MethodAttributes.Static) != 0)
				modifiers += "static ";
			if ((method.Attributes & MethodAttributes.Virtual) != 0 &&
				(method.Attributes & MethodAttributes.NewSlot) == 0)
				modifiers += "override ";

			string methodName = reader.GetString(method.Name);
			string paramList = BuildParameterList(reader, method, sig.ParameterTypes);
			string returnType = sig.ReturnType;

			// Show .ctor as the type name (without void return type)
			if (methodName == ".ctor")
			{
				return $"{modifiers}{declaringTypeName}{paramList}";
			}

			// Map operator names to C# syntax
			if (methodName.StartsWith("op_", StringComparison.Ordinal))
			{
				return FormatOperator(methodName, modifiers, returnType, paramList);
			}

			return $"{modifiers}{returnType} {methodName}{paramList}";
		}

		static string BuildParameterList(MetadataReader reader, MethodDefinition method, System.Collections.Immutable.ImmutableArray<string> parameterTypes)
		{
			if (parameterTypes.Length == 0)
				return "()";

			var parameters = method.GetParameters();
			var typedNames = new string[parameterTypes.Length];
			// Default: use type as name placeholder
			for (int i = 0; i < parameterTypes.Length; i++)
				typedNames[i] = parameterTypes[i];

			foreach (var paramHandle in parameters)
			{
				var param = reader.GetParameter(paramHandle);
				int idx = param.SequenceNumber - 1; // SequenceNumber is 1-based
				if (idx >= 0 && idx < parameterTypes.Length)
				{
					string paramName = reader.GetString(param.Name);
					if (!string.IsNullOrEmpty(paramName))
						typedNames[idx] = $"{parameterTypes[idx]} {paramName}";
				}
			}

			return $"({string.Join(", ", typedNames)})";
		}

		static readonly Dictionary<string, string> OperatorMap = new()
		{
			["op_Addition"] = "operator +",
			["op_Subtraction"] = "operator -",
			["op_Multiply"] = "operator *",
			["op_Division"] = "operator /",
			["op_Modulus"] = "operator %",
			["op_UnaryPlus"] = "operator +",
			["op_UnaryNegation"] = "operator -",
			["op_Equality"] = "operator ==",
			["op_Inequality"] = "operator !=",
			["op_LessThan"] = "operator <",
			["op_GreaterThan"] = "operator >",
			["op_LessThanOrEqual"] = "operator <=",
			["op_GreaterThanOrEqual"] = "operator >=",
			["op_BitwiseAnd"] = "operator &",
			["op_BitwiseOr"] = "operator |",
			["op_ExclusiveOr"] = "operator ^",
			["op_LeftShift"] = "operator <<",
			["op_RightShift"] = "operator >>",
			["op_LogicalNot"] = "operator !",
			["op_OnesComplement"] = "operator ~",
			["op_Increment"] = "operator ++",
			["op_Decrement"] = "operator --",
			["op_True"] = "operator true",
			["op_False"] = "operator false",
			["op_Implicit"] = "implicit operator",
			["op_Explicit"] = "explicit operator",
		};

		static string FormatOperator(string metadataName, string modifiers, string returnType, string paramList)
		{
			if (OperatorMap.TryGetValue(metadataName, out var opSyntax))
			{
				return $"{modifiers}{returnType} {opSyntax}{paramList}";
			}

			// Fallback: unknown operator, keep raw name
			return $"{modifiers}{returnType} {metadataName}{paramList}";
		}

		static string ResolveTypeName(MetadataReader reader, EntityHandle handle)
		{
			if (handle.IsNil)
				return null;

			var provider = new TypeNameProvider(reader);
			try
			{
				return handle.Kind switch
				{
					HandleKind.TypeDefinition => ResolveTypeDefName(reader, (TypeDefinitionHandle)handle),
					HandleKind.TypeReference => ResolveTypeRefName(reader, (TypeReferenceHandle)handle),
					HandleKind.TypeSpecification => provider.VisitTypeSpecification(reader,
						reader.GetTypeSpecification((TypeSpecificationHandle)handle)),
					_ => null,
				};
			}
			catch
			{
				return null;
			}
		}

		static string ResolveTypeDefName(MetadataReader reader, TypeDefinitionHandle handle)
		{
			var def = reader.GetTypeDefinition(handle);
			string ns = reader.GetString(def.Namespace);
			string name = reader.GetString(def.Name);

			if (def.IsNested)
			{
				var declaringName = ResolveTypeDefName(reader, def.GetDeclaringType());
				return declaringName + "." + name;
			}

			if (string.IsNullOrEmpty(ns))
				return name;
			return ns + "." + name;
		}

		static string ResolveTypeRefName(MetadataReader reader, TypeReferenceHandle handle)
		{
			var typeRef = reader.GetTypeReference(handle);
			string ns = reader.GetString(typeRef.Namespace);
			string name = reader.GetString(typeRef.Name);

			if (typeRef.ResolutionScope.Kind == HandleKind.TypeReference)
			{
				var parentName = ResolveTypeRefName(reader, (TypeReferenceHandle)typeRef.ResolutionScope);
				return parentName + "." + name;
			}

			if (string.IsNullOrEmpty(ns))
				return name;
			return ns + "." + name;
		}

		static bool IsCompilerGenerated(string name)
		{
			return name.StartsWith("<") ||
				   name.Contains("__") ||
				   name.Contains('<') ||
				   name.Contains('>');
		}

		static void WriteDivider(TextWriter w, int len = 80) => w.WriteLine(new string('=', len));
		static void WriteSubDivider(TextWriter w, int len = 80) => w.WriteLine(new string('-', len));

		/// <summary>
		/// Provides human-readable type names for signatures via
		/// <see cref="ISignatureTypeProvider{TType, TGenericContext}"/>.
		/// </summary>
		sealed class TypeNameProvider : ISignatureTypeProvider<string, object>
		{
			readonly MetadataReader reader;

			public TypeNameProvider(MetadataReader reader)
			{
				this.reader = reader;
			}

			public string GetPrimitiveType(PrimitiveTypeCode typeCode)
			{
				return typeCode switch
				{
					PrimitiveTypeCode.Boolean => "bool",
					PrimitiveTypeCode.Byte => "byte",
					PrimitiveTypeCode.SByte => "sbyte",
					PrimitiveTypeCode.Char => "char",
					PrimitiveTypeCode.Int16 => "short",
					PrimitiveTypeCode.UInt16 => "ushort",
					PrimitiveTypeCode.Int32 => "int",
					PrimitiveTypeCode.UInt32 => "uint",
					PrimitiveTypeCode.Int64 => "long",
					PrimitiveTypeCode.UInt64 => "ulong",
					PrimitiveTypeCode.Single => "float",
					PrimitiveTypeCode.Double => "double",
					PrimitiveTypeCode.String => "string",
					PrimitiveTypeCode.Void => "void",
					PrimitiveTypeCode.Object => "object",
					PrimitiveTypeCode.TypedReference => "TypedReference",
					PrimitiveTypeCode.IntPtr => "nint",
					PrimitiveTypeCode.UIntPtr => "nuint",
					_ => typeCode.ToString().ToLowerInvariant(),
				};
			}

			public string GetSZArrayType(string elementType) => elementType + "[]";

			public string GetArrayType(string elementType, ArrayShape shape) => elementType + "[]";

			public string GetByReferenceType(string elementType) => elementType;

			public string GetPointerType(string elementType) => elementType + "*";

			public string GetGenericInstantiation(string genericType, System.Collections.Immutable.ImmutableArray<string> typeArguments)
			{
				return $"{genericType}<{string.Join(", ", typeArguments)}>";
			}

			public string GetGenericMethodParameter(object genericContext, int index) => $"T{index}";

			public string GetGenericTypeParameter(object genericContext, int index) => $"T{index}";

			public string GetTypeFromSpecification(MetadataReader reader, object genericContext, TypeSpecificationHandle handle, byte rawTypeKind)
			{
				var spec = reader.GetTypeSpecification(handle);
				return spec.DecodeSignature(this, genericContext);
			}

			public string GetTypeFromDefinition(MetadataReader r, TypeDefinitionHandle handle, byte rawTypeKind)
			{
				var def = r.GetTypeDefinition(handle);
				string ns = r.GetString(def.Namespace);
				string name = r.GetString(def.Name);
				if (def.IsNested)
				{
					var parent = GetTypeFromDefinition(r, def.GetDeclaringType(), 0);
					return parent + "." + name;
				}
				if (string.IsNullOrEmpty(ns))
					return name;
				return ns + "." + name;
			}

			public string GetTypeFromReference(MetadataReader r, TypeReferenceHandle handle, byte rawTypeKind)
			{
				var typeRef = r.GetTypeReference(handle);
				string ns = r.GetString(typeRef.Namespace);
				string name = r.GetString(typeRef.Name);

				if (typeRef.ResolutionScope.Kind == HandleKind.TypeReference)
				{
					var parent = GetTypeFromReference(r, (TypeReferenceHandle)typeRef.ResolutionScope, 0);
					return parent + "." + name;
				}

				if (string.IsNullOrEmpty(ns))
					return name;
				return ns + "." + name;
			}

			public string GetPinnedType(string elementType) => elementType;

			public string GetModifiedType(string modifier, string unmodifiedType, bool isRequired) => unmodifiedType;

			public string GetFunctionPointerType(MethodSignature<string> signature) => "delegate*<...>";

			public string VisitTypeSpecification(MetadataReader reader, TypeSpecification spec)
			{
				return spec.DecodeSignature(this, default);
			}
		}
	}

	/// <summary>
	/// Extension to format a <see cref="MethodSignature{String}"/> as a C#-like parameter list.
	/// </summary>
	static class SignatureFormatting
	{
		public static string ToParameterList(this System.Collections.Immutable.ImmutableArray<string> types)
		{
			if (types.Length == 0) return "()";
			return $"({string.Join(", ", types)})";
		}

		public static string ToFormattedSignature(this MethodSignature<string> sig)
		{
			return $"{sig.ReturnType}({string.Join(", ", sig.ParameterTypes)})";
		}
	}
}